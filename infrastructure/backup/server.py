import json
import os
import re
import subprocess
import time
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = os.environ["BACKUP_TOKEN"]

PGHOST = os.environ["PGHOST"]
PGPORT = os.environ.get("PGPORT", "5000")
PGUSER = os.environ["PGUSER"]
PGDATABASE = os.environ["PGDATABASE"]

DIR = "/backups"

PG_ENV = os.environ.copy()
PG_ENV["PGSSLMODE"] = "disable"

TABLES = (
    "cart_items",
    "carts",
    "categories",
    "order_items",
    "orders",
    "products",
    "users",
)


def run(cmd):
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=PG_ENV,
            timeout=3600,
            check=False
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(
            cmd, 1, "", str(exc)
        )


def psql(db, query):
    return run([
        "psql",
        "-X",
        "-v", "ON_ERROR_STOP=1",
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        "-d", db,
        "-t",
        "-A",
        "-c", query
    ])


def get_counts(db):
    query = """
        SELECT json_build_object(
            'cart_items', (SELECT COUNT(*) FROM public.cart_items),
            'carts', (SELECT COUNT(*) FROM public.carts),
            'categories', (SELECT COUNT(*) FROM public.categories),
            'order_items', (SELECT COUNT(*) FROM public.order_items),
            'orders', (SELECT COUNT(*) FROM public.orders),
            'products', (SELECT COUNT(*) FROM public.products),
            'users', (SELECT COUNT(*) FROM public.users)
        )::text;
    """

    result = psql(db, query)

    if result.returncode != 0:
        return None, result.stderr[-500:]

    try:
        counts = json.loads(result.stdout.strip())
        return counts, None
    except (ValueError, TypeError):
        return None, "No se pudieron interpretar los conteos."


def do_backup():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.dump"
    filepath = os.path.join(DIR, filename)

    started = time.time()

    os.makedirs(DIR, exist_ok=True)

    result = run([
        "pg_dump",
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        "-Fc",
        "-Z", "6",
        "-f", filepath,
        PGDATABASE
    ])

    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    ok = result.returncode == 0 and size > 1000

    if not ok and os.path.exists(filepath):
        os.remove(filepath)

    return {
        "status": "ok" if ok else "error",
        "file": filename,
        "size": size,
        "seconds": round(time.time() - started, 1),
        "error": result.stderr[-500:] if not ok else None
    }


def do_restore_test(name):
    if not isinstance(name, str) or not re.fullmatch(
        r"backup_\d{8}_\d{6}\.dump",
        name
    ):
        return {
            "status": "error",
            "error": "nombre invalido"
        }

    filepath = os.path.join(DIR, name)

    if not os.path.isfile(filepath):
        return {
            "status": "error",
            "error": "el archivo no existe"
        }

    started = time.time()

    restore_db = f"restore_test_{os.getpid()}_{time.time_ns()}"

    expected_counts, count_error = get_counts(PGDATABASE)

    if expected_counts is None:
        return {
            "status": "error",
            "error": count_error
        }

    expected = expected_counts["products"]

    created = run([
        "createdb",
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        restore_db
    ])

    if created.returncode != 0:
        return {
            "status": "error",
            "rows": -1,
            "expected": expected,
            "seconds": round(time.time() - started, 1),
            "error": created.stderr[-500:]
        }

    restore = run([
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        "-d", restore_db,
        filepath
    ])

    actual_counts = None
    actual_error = None

    if restore.returncode == 0:
        actual_counts, actual_error = get_counts(restore_db)

    dropped = run([
        "dropdb",
        "--if-exists",
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        restore_db
    ])

    rows = (
        actual_counts["products"]
        if actual_counts is not None
        else -1
    )

    ok = (
        restore.returncode == 0
        and actual_counts is not None
        and actual_counts == expected_counts
        and dropped.returncode == 0
    )

    error = None

    if restore.returncode != 0:
        error = restore.stderr[-500:]
    elif actual_error:
        error = actual_error
    elif dropped.returncode != 0:
        error = dropped.stderr[-500:]

    return {
        "status": "ok" if ok else "error",
        "rows": rows,
        "expected": expected,
        "seconds": round(time.time() - started, 1),
        "error": error,
        "table_counts": {
            "actual": actual_counts,
            "expected": expected_counts
        }
    }


class Handler(BaseHTTPRequestHandler):

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        auth = self.headers.get("Authorization", "")

        if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
            return self.reply(401, {
                "status": "error",
                "error": "no autorizado"
            })

        n = int(self.headers.get("Content-Length", 0))

        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.reply(400, {
                "status": "error",
                "error": "JSON invalido"
            })

        if self.path == "/backup":
            self.reply(200, do_backup())

        elif self.path == "/restore-test":
            self.reply(200, do_restore_test(data.get("file", "")))

        else:
            self.reply(404, {
                "status": "error",
                "error": "ruta no encontrada"
            })


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()