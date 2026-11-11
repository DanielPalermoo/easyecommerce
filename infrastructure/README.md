# EasyCommerce - Infraestructura

Módulo de infraestructura consolidado del TP integrador de HIA. Levanta la tienda
(PostgreSQL + backend Spring Boot + frontend Nginx) y las herramientas de apoyo
(Prometheus, Grafana, pgAdmin, n8n, Jira) con Docker Compose.

## Requisitos

- Docker Desktop o Docker Engine (WSL2 / Linux) en ejecución.
- Repositorios clonados lado a lado:

```
carpeta-del-tp/
├── easyecommerce/                 (backend con infraestructura consolidada)
│   └── infrastructure/            (este directorio con los compose)
└── ecommerce-front/               (frontend React)
```

## Dos archivos compose

| Archivo | Qué contiene | Cuándo se usa |
|---|---|---|
| `docker-compose.yml` | db, app (backend), frontend | Siempre. Es lo que se despliega |
| `docker-compose.tools.yml` | Prometheus, Grafana, exporters, pgAdmin, n8n, Jira | Solo para trabajar y monitorear |
| `docker-compose.override.yml` | Abre puertos en tu PC | Solo en local; Compose lo lee solo |

Las herramientas se conectan a la red de la tienda (`easycommerce-network`),
por eso **siempre se levanta primero la tienda**.

## 1. Levantar la tienda

```powershell
copy .env.example .env      # en Linux/Mac: cp .env.example .env
```

Abrí `.env` y reemplazá todos los valores `cambiar_esto` por contraseñas reales.
El `.env` **no se sube a GitHub**: cada integrante tiene el suyo.

```powershell
docker compose up -d --build
docker compose ps
docker compose logs app --tail 20
```

En el log del backend tiene que aparecer `Started EasyecommerceApplication`.

| Servicio | Dirección local |
|---|---|
| Frontend | http://localhost:8082 |
| Backend (Swagger) | http://localhost:8081/swagger-ui/index.html |
| PostgreSQL (clientes externos) | localhost:5433 |

## 2. Levantar las herramientas

Con la tienda ya corriendo, de a un grupo por vez (cada comando lleva `-f`):

```powershell
docker compose -f docker-compose.tools.yml up -d prometheus grafana postgres-exporter
docker compose -f docker-compose.tools.yml up -d pgadmin n8n
docker compose -f docker-compose.tools.yml up -d jira-db jira
```

| Herramienta | Dirección | Acceso |
|---|---|---|
| Prometheus | http://localhost:9090 | Sin login |
| Grafana | http://localhost:3000 | Usuario y contraseña del `.env` |
| pgAdmin | http://localhost:5050 | Email y contraseña del `.env` |
| n8n | http://localhost:5678 | Cuenta propia, se crea al entrar la primera vez |
| Jira | http://localhost:8080 | Asistente de configuración y licencia de prueba |

Conexiones entre herramientas (siempre por nombre de servicio, no por `localhost`):

- Grafana → Prometheus: `http://prometheus:9090`
- pgAdmin → base: host `db`, puerto `5432`, usuario `postgres`, contraseña del `.env`

`node-exporter` y `cadvisor` están en el perfil `linux`: se usan solo en el
servidor Linux (`--profile linux`), porque en Windows miden la VM de Docker.

## Detener servicios

```powershell
docker compose down
docker compose -f docker-compose.tools.yml down
```

Los datos se conservan en volúmenes. **No uses `down -v` si la base ya tiene datos**:
borra los volúmenes (en n8n también se pierden los flujos y la cuenta).

## Seguridad

- El `.env` real nunca se sube; en el repo solo está `.env.example`.
- En el compose base ningún servicio abre puertos; los puertos locales
  (siempre en `127.0.0.1`) los abre el `override`, que no se usa en el servidor.
- Las imágenes tienen versión fija.

## Estado y pendientes

- El front llama directo a `http://localhost:8081` y el navegador lo bloquea por CORS.
  Solución prevista: que el Nginx del front reenvíe `/api` al backend.
- Para que el target `backend` de Prometheus pase de DOWN a UP, falta agregar
  Actuator y Micrometer al `pom.xml` del backend.
- `-DskipTests` se usa en el build del backend para la primera puesta en marcha;
  en CI/CD hay que ejecutar los tests y bloquear el build si fallan.