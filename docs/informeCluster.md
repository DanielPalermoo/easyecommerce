# EasyCommerce - Alta disponibilidad de PostgreSQL

## 1. Objetivo

Este documento registra la arquitectura de alta disponibilidad (HA) de PostgreSQL integrada en EasyCommerce y las verificaciones realizadas durante la migración y la prueba de cambio planificado de líder (*switchover*).

La solución utiliza Patroni para administrar los nodos PostgreSQL, etcd como almacén de coordinación y HAProxy como punto de entrada para los clientes de base de datos.

> **Estado de la validación:** el switchover planificado de `patroni1` a `patroni2` se completó correctamente. El nuevo líder quedó operativo, el nodo anterior se reincorporó como réplica con retraso cero y Spring Boot continuó respondiendo. Se verificó que HAProxy conectaba al nuevo primario. Una escritura de negocio posterior al failover debe registrarse como prueba adicional cuando se ejecute explícitamente.

## 2. Arquitectura

### Componentes

| Componente | Responsabilidad |
|---|---|
| PostgreSQL + Patroni 1 | Nodo PostgreSQL administrado por Patroni. Puede actuar como líder o réplica. |
| PostgreSQL + Patroni 2 | Segundo nodo PostgreSQL administrado por Patroni. Puede actuar como líder o réplica. |
| etcd 1, 2 y 3 | Almacén distribuido de coordinación y estado del clúster Patroni. |
| HAProxy | Punto de entrada TCP para las conexiones PostgreSQL. Comprueba el endpoint REST `/primary` de Patroni para enviar conexiones al líder. |
| Spring Boot (`easycommerce-app`) | Backend de EasyCommerce. Se conecta a PostgreSQL a través de HAProxy. |
| postgres-exporter | Expone métricas de PostgreSQL para Prometheus. |
| db-backup | Servicio de copias de seguridad y restauración de la base de datos. |
| Prometheus / Grafana | Recolección y visualización de métricas. |

### Flujo de conexión

```text
Navegador
   |
   v
Frontend EasyCommerce
   |
   v
Spring Boot (easycommerce-app)
   |
   v
HAProxy (haproxy:5000)
   |
   +----> Patroni 1 (líder o réplica)
   |
   +----> Patroni 2 (líder o réplica)
              |
              v
       PostgreSQL primario
```

HAProxy comprueba el endpoint REST `/primary` de cada nodo Patroni. El nodo que no es primario no debe recibir conexiones de escritura a través del backend `postgres_primary`.

La coordinación del clúster se apoya en los tres miembros de etcd.

## 3. Configuración de conexión de la aplicación

La aplicación Spring Boot utiliza HAProxy como destino JDBC:

```text
jdbc:postgresql://haproxy:5000/easyecommerce?options=-c%20timezone=UTC
```

Las credenciales se inyectan mediante variables de entorno definidas en el archivo `.env` de infraestructura. Los valores secretos no deben incluirse en este documento ni subirse al repositorio.

Variables utilizadas por el servicio de aplicación:

- `DB_NAME`: URL JDBC que apunta a `haproxy:5000`.
- `DB_USER`: usuario de aplicación.
- `DB_PASSWORD`: contraseña del usuario de aplicación.
- `PORT`: puerto interno de Spring Boot (`8081`).
- `SQL_INIT_MODE`: configurado como `never` para evitar inicializaciones automáticas no deseadas durante esta integración.

El servicio `app` y HAProxy comparten la red Docker `easycommerce-network`, lo que permite resolver el nombre DNS `haproxy` desde el contenedor de Spring Boot.

## 4. Roles de base de datos

Se utilizan usuarios separados para reducir privilegios:

| Usuario | Uso |
|---|---|
| `easyecommerce_app` | Conexión de la aplicación y operaciones propias del esquema de EasyCommerce. |
| `easyecommerce_backup` | Consultas y operaciones necesarias para copias de seguridad y verificación de restauración. |

Las contraseñas se guardan en archivos de entorno ignorados por Git. No deben copiarse a documentación, scripts versionados ni capturas públicas.

## 5. Migración y verificación de datos

La base migrada se llama `easyecommerce`.

Durante la verificación de la migración se comprobaron:

- Las siete tablas principales: `cart_items`, `carts`, `categories`, `order_items`, `orders`, `products` y `users`.
- Los índices, claves primarias, restricciones únicas y claves foráneas.
- Las secuencias asociadas a columnas identity.
- Las extensiones `pgcrypto` y `plpgsql`.
- La lectura de datos mediante el usuario de aplicación.
- La conexión al primario a través de HAProxy.

Se generó una copia de seguridad y se ejecutó una prueba de restauración. La restauración de prueba informó que la cantidad de filas restauradas coincidía con la cantidad esperada en ese momento.

Las cantidades de filas pueden cambiar por las operaciones normales de la aplicación; por eso no se fijan aquí como valores permanentes.

## 6. Configuración de HAProxy

Archivo de configuración:

```text
infrastructure/ha/haproxy/haproxy.cfg
```

Configuración funcional utilizada:

```haproxy
global
    log stdout format raw local0
    maxconn 256

defaults
    log global
    mode tcp
    option tcplog

    timeout connect 5s
    timeout client 1h
    timeout server 1h

frontend postgres_front
    bind *:5000
    default_backend postgres_primary

backend postgres_primary
    option httpchk
    http-check send meth GET uri /primary ver HTTP/1.1
    http-check expect status 200

    default-server inter 3s fall 3 rise 2

    server patroni1 patroni1:5432 check port 8008
    server patroni2 patroni2:5432 check port 8008

frontend stats
    bind *:7000
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
```

El puerto `5000` es el punto de entrada TCP de PostgreSQL para los servicios Docker. El puerto `7000` expone la página de estadísticas de HAProxy; en el entorno verificado se publicó únicamente en `127.0.0.1`.

## 7. Exportación de métricas y backups

### postgres-exporter

El exporter se conecta a PostgreSQL mediante HAProxy:

```text
haproxy:5000/easyecommerce?sslmode=disable
```

Se deshabilitó el colector WAL (`--no-collector.wal`) porque el usuario de monitorización no dispone de permisos para ejecutar `pg_ls_waldir`. Después del ajuste, el exporter quedó operativo y `pg_up` informó `1`.

### db-backup

El servicio de backup también utiliza HAProxy como destino:

- `PGHOST=haproxy`
- `PGPORT=5000`
- `PGDATABASE=easyecommerce`

Las credenciales y el token de autenticación se proporcionan mediante variables de entorno. Se verificó una operación autenticada de backup y una restauración de prueba. También se comprobó que una solicitud sin autenticación recibiera HTTP `401`.

El backup de aplicación no reemplaza las copias físicas o los mecanismos de recuperación que puedan formar parte de la estrategia de infraestructura.

## 8. Prueba de switchover planificado

### Estado inicial

Antes de la prueba, `patronictl list` informó:

| Nodo | Rol | Estado | Timeline | Retraso |
|---|---|---|---:|---:|
| patroni1 | Leader | running | 3 | — |
| patroni2 | Replica | streaming | 3 | 0 |

Se verificó que la réplica estuviera sincronizada antes de iniciar el cambio.

### Comando utilizado

Primero se consultó la ayuda de `patronictl switchover` para confirmar la sintaxis de la versión instalada.

Luego se ejecutó:

```powershell
docker exec -it easycommerce-ha-patroni1 patronictl -c /etc/patroni/patroni.yml switchover easycommerce-ha --leader patroni1 --candidate patroni2
```

En el prompt de programación se eligió `now`. No se utilizó `--force`; la operación se realizó mediante el flujo interactivo de confirmación de Patroni.

### Resultado

Los registros de Patroni 1 mostraron que:

1. Recibió la solicitud de switchover con `patroni1` como líder y `patroni2` como candidato.
2. Ejecutó una degradación ordenada (*graceful demotion*).
3. Liberó el bloqueo de líder.
4. Detectó que `patroni2` había adquirido el liderazgo.
5. Arrancó PostgreSQL en modo standby.
6. Obtuvo el archivo de historial de la nueva timeline y comenzó a seguir la timeline 4.
7. Continuó como réplica de `patroni2`.

El contenedor de Patroni 1 permaneció `Up`; el estado `stopped` que apareció brevemente en la primera tabla correspondía a la transición del proceso PostgreSQL durante la degradación, no a un contenedor Docker detenido.

### Estado final del clúster

La consulta posterior a través de Patroni 2 devolvió:

| Nodo | Rol | Estado | Timeline | Receive LSN | Replay LSN | Retraso |
|---|---|---|---:|---|---|---:|
| patroni1 | Replica | streaming | 4 | `0/990EEA00` | `0/990EEA00` | 0 |
| patroni2 | Leader | running | 4 | — | — | — |

Los dos nodos quedaron en timeline 4 y la réplica informó retraso cero.

## 9. Verificaciones posteriores al switchover

### Salud de Spring Boot

Comando ejecutado desde PowerShell:

```powershell
docker run --rm --network easycommerce-network busybox:1.36 wget -S -O - http://easycommerce-app:8081/actuator/health
```

Resultado observado:

```text
HTTP/1.1 200
{"status":"UP"}
```

Esto confirma que el backend seguía respondiendo después del cambio de líder.

### Identificación del primario a través de HAProxy

Comando ejecutado:

```powershell
docker exec easycommerce-db-backup psql -h haproxy -p 5000 -U easyecommerce_backup -d easyecommerce -c "SELECT pg_is_in_recovery(), inet_server_addr(), current_timestamp;"
```

Resultado observado:

```text
pg_is_in_recovery | inet_server_addr
------------------+-----------------
f                 | 172.30.50.12
```

`pg_is_in_recovery = false` indica que la conexión llegó a un servidor que está actuando como primario. La dirección `172.30.50.12` correspondió al nuevo líder `patroni2` en la topología observada.

### Pruebas funcionales de la aplicación

Antes del switchover se probaron desde el frontend y el administrador las funciones de EasyCommerce, incluyendo autenticación, productos, carrito y pedidos. También se comprobó el frontend con HTTP `200`.

Después del switchover se verificó el estado HTTP del backend y la conexión a través de HAProxy al nuevo primario.

**Prueba adicional pendiente de registrar:** realizar una escritura de negocio nueva después del switchover (por ejemplo, crear un producto de prueba), confirmar que se conserva y comprobar que se replica al nodo secundario. La consulta `pg_is_in_recovery() = false` verifica que el destino es primario, pero por sí sola no demuestra una escritura de negocio.

## 10. Comandos de diagnóstico útiles

Ejecutar desde la carpeta `infrastructure` en PowerShell.

### Estado del clúster

```powershell
docker exec easycommerce-ha-patroni2 patronictl -c /etc/patroni/patroni.yml list
```

### Logs de Patroni

```powershell
docker logs --tail 100 easycommerce-ha-patroni1
docker logs --tail 100 easycommerce-ha-patroni2
```

### Salud del backend

```powershell
docker run --rm --network easycommerce-network busybox:1.36 wget -S -O - http://easycommerce-app:8081/actuator/health
```

### Comprobar qué nodo atiende a través de HAProxy

```powershell
docker exec easycommerce-db-backup psql -h haproxy -p 5000 -U easyecommerce_backup -d easyecommerce -c "SELECT pg_is_in_recovery(), inet_server_addr(), current_timestamp;"
```

El comando solicita la contraseña del usuario de backup si no está disponible en el entorno del contenedor. No incluir contraseñas en el historial de documentación ni en Git.

### Estado de contenedores

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml ps
docker compose -f .\ha\docker-compose.ha.yml ps
```

Antes de usar estos comandos, verificar que los archivos Compose y de entorno correspondan a la configuración actual del proyecto.

## 11. Procedimiento general para una prueba de switchover

> Realizar esta operación solamente en un entorno controlado, con una copia de seguridad válida y una réplica sincronizada. Un switchover planificado no equivale a una prueba de caída abrupta del servidor.

1. Verificar el estado de los miembros con `patronictl list`.
2. Confirmar que el líder esté `running`, que la réplica esté `streaming` y que el retraso sea cero.
3. Confirmar que exista una copia de seguridad válida y reciente.
4. Consultar `patronictl switchover --help` para conocer la sintaxis de la versión instalada.
5. Ejecutar el switchover indicando líder y candidato correctos, sin `--force`.
6. Confirmar el cambio en el prompt interactivo.
7. Esperar a que el candidato sea `Leader` y el antiguo líder vuelva como `Replica`.
8. Confirmar que ambos nodos estén en la misma timeline y que el retraso sea cero.
9. Verificar la salud del backend y la conexión a través de HAProxy.
10. Ejecutar una operación de negocio de escritura y comprobar su persistencia y replicación.

No ejecutar `docker compose down -v`, eliminar volúmenes ni borrar el directorio de datos como parte de esta prueba.

## 12. Estado y alcance de la validación

### Comprobado

- Clúster Patroni con dos nodos PostgreSQL.
- Coordinación mediante tres miembros etcd.
- Réplica sincronizada antes del switchover.
- Switchover planificado de `patroni1` a `patroni2`.
- Reincorporación de `patroni1` como réplica.
- Timeline 4 en ambos nodos y retraso cero.
- HAProxy encaminando la conexión al nuevo primario.
- Spring Boot respondiendo HTTP `200` y estado `UP`.
- Backup y restauración de prueba verificados antes del switchover.
- Pruebas funcionales de la aplicación realizadas antes del switchover.

### No afirmar como probado todavía

- Failover automático ante una caída abrupta de hardware o de un contenedor.
- Cero interrupción de solicitudes durante el cambio de líder.
- Escritura de negocio nueva posterior al switchover y su posterior replicación, hasta ejecutar y registrar esa prueba.
- Recuperación ante pérdida simultánea de varios miembros de etcd.

La prueba documentada aquí es un **switchover planificado**, no una simulación de todos los escenarios posibles de desastre.

## 13. Seguridad y versionado

- No versionar `.env`, contraseñas, tokens, claves privadas ni dumps de base de datos.
- Mantener los archivos de entorno excluidos mediante `../.gitignore`.
- Revisar `git status` y el diff antes de crear el commit.
- No incluir archivos de backup ni datos reales de clientes en el repositorio.
- Revisar que la documentación no contenga credenciales ni información sensible antes de publicarla.

---

**Resumen:** EasyCommerce completó un switchover planificado de PostgreSQL desde `patroni1` hacia `patroni2`. El nodo anterior se reincorporó como réplica sincronizada, HAProxy conectó al nuevo primario y Spring Boot continuó respondiendo. La prueba adicional de escritura de negocio posterior al cambio debe completarse para cerrar también esa evidencia funcional.
