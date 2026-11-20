# EasyCommerce - Infraestructura Docker

## 1. Descripción

Este directorio contiene la infraestructura necesaria para ejecutar EasyCommerce mediante Docker Compose.

El entorno incluye:

- Backend desarrollado con Spring Boot.
- Frontend de EasyCommerce.
- PostgreSQL con alta disponibilidad mediante Patroni.
- etcd para coordinación del clúster.
- HAProxy para dirigir las conexiones hacia el nodo PostgreSQL primario.
- Prometheus y Grafana para monitoreo.
- PostgreSQL Exporter para métricas de base de datos.
- Servicio de backups y restauración.
- Servicios auxiliares como n8n, MantisBT y pgAdmin.

La infraestructura está dividida en dos archivos Docker Compose para separar la aplicación de la infraestructura de base de datos.

## 2. Arquitectura

### Compose principal

Archivo:

`docker-compose.yml`

Administra los servicios de aplicación y herramientas auxiliares:

- Spring Boot.
- Frontend.
- n8n.
- Prometheus.
- Grafana.
- PostgreSQL Exporter.
- Servicio de backups.
- MantisBT.
- pgAdmin.
- Otros servicios auxiliares definidos en el Compose.

Red principal:

`easycommerce-network`

### Compose de alta disponibilidad

Archivo:

`ha/docker-compose.ha.yml`

Administra los componentes del clúster PostgreSQL:

- Patroni 1.
- Patroni 2.
- etcd 1.
- etcd 2.
- etcd 3.
- HAProxy.

Red del clúster:

`easycommerce-ha-network`

HAProxy participa en ambas redes para permitir la comunicación entre los servicios de aplicación y los nodos PostgreSQL.

## 3. Requisitos previos

Antes de iniciar el entorno se necesita:

- Docker Desktop instalado.
- Docker Compose disponible mediante `docker compose`.
- Git.
- Acceso a Internet para descargar las imágenes Docker.
- Recursos suficientes de memoria y almacenamiento para ejecutar los contenedores.

Se recomienda utilizar Windows con Docker Desktop y WSL 2, aunque el entorno puede adaptarse a otros sistemas compatibles con Docker.

## 4. Configuración inicial

Clonar el repositorio:

```powershell
git clone URL_DEL_REPOSITORIO
```

Ingresar al directorio de infraestructura:

```powershell
cd easyecommerce/infrastructure
```

Crear los archivos de variables de entorno a partir de sus respectivas plantillas:

- `.env.example` → `.env`
- `ha/.env.example` → `ha/.env`

Completar los valores requeridos en cada archivo.

Los archivos `.env` contienen credenciales y configuraciones privadas. No deben subirse al repositorio.

Cada integrante debe utilizar sus propias credenciales locales y verificar que los nombres de las variables coincidan con los requeridos por los archivos Compose.

## 5. Orden de inicio

La infraestructura utiliza dos archivos Compose independientes.

**Importante:** primero debe iniciarse el clúster PostgreSQL HA y comprobar que tenga un líder disponible. Después se inicia la aplicación.

Todos los comandos siguientes se ejecutan desde el directorio `infrastructure`.

### Paso 1. Iniciar PostgreSQL HA

```powershell
docker compose --env-file .\ha\.env -f .\ha\docker-compose.ha.yml up -d
```

Este comando inicia los nodos Patroni, los miembros etcd y HAProxy.

### Paso 2. Verificar el clúster

Consultar el estado de Patroni:

```powershell
docker exec easycommerce-ha-patroni1 patronictl -c /etc/patroni/patroni.yml list
```

El resultado esperado es:

- Un nodo con rol `Leader` y estado `running`.
- Un nodo con rol `Replica` y estado `streaming`.
- Retraso de replicación idealmente igual a cero.

No continuar con el inicio de la aplicación hasta que el clúster tenga un líder operativo.

### Paso 3. Iniciar EasyCommerce

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml up -d --build
```

Este comando construye e inicia el backend y los servicios auxiliares definidos en el Compose principal.

### Paso 4. Comprobar los contenedores

Para consultar los servicios principales:

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml ps
```

Para consultar el clúster HA:

```powershell
docker compose --env-file .\ha\.env -f .\ha\docker-compose.ha.yml ps
```

## 6. Verificaciones

### Estado del clúster PostgreSQL

```powershell
docker exec easycommerce-ha-patroni1 patronictl -c /etc/patroni/patroni.yml list
```

### Salud del backend

Desde la red Docker principal:

```powershell
docker run --rm --network easycommerce-network busybox:1.36 wget -S -O - http://easycommerce-app:8081/actuator/health
```

Respuesta esperada:

```json
{"status":"UP"}
```

### Frontend

Si se mantienen los puertos configurados actualmente:

```text
http://localhost:8082
```

### Prometheus

```text
http://localhost:9090
```

### Grafana

```text
http://localhost:3000
```

### n8n

```text
http://localhost:5678
```

Los puertos y servicios disponibles dependen de la configuración vigente de los archivos Compose.

## 7. Conexión de Spring Boot a PostgreSQL

Spring Boot se conecta a PostgreSQL mediante HAProxy, no directamente a uno de los nodos Patroni.

La conexión JDBC utiliza el nombre DNS del servicio:

```text
jdbc:postgresql://haproxy:5000/easyecommerce?options=-c%20timezone=UTC
```

De esta manera, cuando cambia el nodo primario, HAProxy puede dirigir las nuevas conexiones hacia el líder disponible.

## 8. Detener los servicios

Se recomienda detener primero la aplicación y después el clúster de base de datos.

### Detener Compose principal

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml down
```

### Detener Compose HA

```powershell
docker compose --env-file .\ha\.env -f .\ha\docker-compose.ha.yml down
```

**Advertencia:** no agregar `-v` al comando `down`, porque podría eliminar los volúmenes asociados y provocar la pérdida de datos persistentes.

## 9. Reiniciar los servicios

Para reiniciar el entorno completo:

1. Iniciar el Compose HA.
2. Verificar el estado del clúster.
3. Iniciar el Compose principal.

Utilizar nuevamente los comandos de la sección 5.

## 10. Documentación técnica

Para conocer en profundidad la implementación de alta disponibilidad, consultar:

`POSTGRESQL_HA_EasyCommerce.md`

Este informe documenta:

- Arquitectura Patroni, etcd y HAProxy.
- Migración de PostgreSQL.
- Roles y permisos.
- Configuración de conexiones.
- Backups y restauración.
- Exportación de métricas.
- Prueba de switchover.
- Verificación de replicación.
- Comprobaciones de Spring Boot.
- Resultados y limitaciones de las pruebas.

## 11. Seguridad

- No subir archivos `.env`.
- No publicar contraseñas, tokens ni claves privadas.
- No versionar dumps de bases de datos.
- No eliminar volúmenes de PostgreSQL sin una copia de seguridad y autorización.
- Utilizar archivos `.env.example` sin credenciales reales.
- Revisar los cambios antes de realizar un commit.

## 12. Consideraciones

La alta disponibilidad de PostgreSQL está implementada mediante Patroni, etcd y HAProxy.

La prueba documentada de cambio de líder es un switchover planificado. No debe confundirse con una prueba de caída abrupta de infraestructura ni interpretarse como garantía de cero interrupciones durante cualquier escenario de fallo.

Para conocer los resultados concretos de las pruebas realizadas, consultar el informe técnico de PostgreSQL HA.

---

**EasyCommerce - Infraestructura Docker**
