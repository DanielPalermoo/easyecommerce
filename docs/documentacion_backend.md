# Documentación del backend de EasyCommerce

EasyCommerce es un backend REST con arquitectura en capas para un sistema de comercio electrónico de pequeña escala. Permite registrar cuentas e iniciar sesión mediante JWT, consultar un catálogo de productos, administrar carritos, realizar compras de forma transaccional, consultar el historial de pedidos y ejecutar operaciones administrativas. Este documento describe el comportamiento implementado en el backend actual desarrollado con Java y Spring Boot; distingue expresamente el comportamiento observado de lo previsto o de lo indicado en documentación anterior.

## Inicio rápido

1. Instalar Java 25 y disponer de PostgreSQL, o utilizar el conjunto de servicios de Docker Compose.
2. Configurar las variables de entorno de la base de datos (`DB_NAME`, `DB_USER` y `DB_PASSWORD`) en lugar de incluir credenciales en el control de versiones.
3. Ejecutar `./mvnw spring-boot:run` (en PowerShell: `./mvnw.cmd spring-boot:run`) o `docker compose -f infrastructure/docker-compose.yml up --build`.
4. Enviar las solicitudes a `http://localhost:8081` cuando se ejecute la aplicación directamente. La interfaz de Swagger UI está disponible en `/swagger-ui/index.html`.

## Propósito y tecnologías utilizadas

| Área | Tecnología implementada |
|---|---|
| Entorno de ejecución | Java 25, Spring Boot 3.5.3 |
| API HTTP | Spring Web MVC, Bean Validation, springdoc OpenAPI/Swagger |
| Persistencia | Spring Data JPA / Hibernate, PostgreSQL en tiempo de ejecución |
| Seguridad | Spring Security, contraseñas cifradas con hash BCrypt, tokens JWT Bearer firmados con HS256 |
| Mapeo | MapStruct 1.5.5.Final y Lombok |
| Operaciones | Actuator, registro de métricas Micrometer Prometheus, Docker Compose |
| Pruebas | JUnit 5, Spring Boot Test, MockMvc, Spring Security Test, H2 en modo de compatibilidad con PostgreSQL |

La aplicación ejecutable establece UTC como zona horaria predeterminada de la JVM. La persistencia en producción utiliza `ddl-auto: update`, mientras que las pruebas emplean una base de datos H2 en memoria con `create-drop`.

## Estructura de paquetes

| Paquete/ruta | Responsabilidad |
|---|---|
| `controller` | Rutas HTTP, selección de códigos de estado de respuesta y anotaciones de autorización por endpoint |
| `Service` | Flujos de negocio para autenticación, productos, categorías, carritos, pedidos y JWT |
| `repository` | Repositorios de Spring Data JPA y consultas derivadas |
| `entity` | Entidades JPA y mapeo de relaciones |
| `dto` | Contratos de solicitudes y respuestas expuestos por la API |
| `mapper` | Conversiones de entidades a DTO con MapStruct y campos calculados de respuesta |
| `configSecurity` | Cadena de filtros de seguridad, CORS, filtro JWT, clave de firma y componentes de autenticación |
| `config` | Configuración del esquema de autenticación Bearer en OpenAPI |
| `exception` | Excepciones de dominio y manejador global de errores de validación y dominio |
| `src/main/resources` | Configuración en tiempo de ejecución y datos iniciales SQL |
| `src/test` | Pruebas de integración, controladores y seguridad con MockMvc y H2 |
| `infrastructure` | Despliegue con Compose, configuración de monitoreo, scripts y volcado del esquema de base de datos |

## Arquitectura y flujo de solicitudes

El recorrido principal de una solicitud es:

```text
Solicitud HTTP
  -> CORS + cadena de filtros de Spring Security
  -> JwtAuthenticationFilter (si se proporciona Authorization: Bearer <token>)
  -> autorización mediante reglas de rutas + @PreAuthorize
  -> controlador REST
  -> transacción del servicio y reglas de negocio
  -> repositorio Spring Data / entidades JPA
  -> PostgreSQL
  -> DTO de respuesta con MapStruct -> respuesta JSON
```

El filtro JWT extrae el correo electrónico utilizado como sujeto del token, vuelve a cargar el objeto `User` desde la base de datos y establece en el contexto de seguridad las autoridades correspondientes a su rol actual. Los controladores no devuelven entidades JPA para los principales recursos del dominio; los servicios las convierten en DTO.

## Descripción general de la API

Todas las rutas de la aplicación que se indican a continuación comienzan con `/api`. Las solicitudes protegidas utilizan `Authorization: Bearer <jwt>`. La paginación utiliza los parámetros de consulta estándar de Spring: `page`, `size` y `sort`.

### Autenticación

| Método y ruta | Acceso | Solicitud | Respuesta / comportamiento |
|---|---|---|---|
| `POST /api/auth/register` | Público | `name`, `email`, `password` (mínimo 6 caracteres), `street`, `city`, `zipCode` | `201` y un mensaje de éxito; las cuentas nuevas reciben el rol `USER` y la contraseña se almacena con hash BCrypt |
| `POST /api/auth/login` | Público | `email`, `password` | `200` con `{ "jwt": "..." }`; el vencimiento del token está configurado en 30 minutos |
| `GET /api/auth/auth-me` | Autenticado | Ninguna | `200` con el ID, nombre, correo, rol y datos de domicilio del usuario actual. La configuración de seguridad rechaza las solicitudes anónimas antes de llegar al controlador; las pruebas de seguridad actuales con MockMvc esperan `403` para este tipo de solicitud protegida. |

### Catálogo y administración de categorías

| Método y ruta | Autoridad requerida | Contrato y resultado |
|---|---|---|
| `GET /api/products` | `READ_ALL_PRODUCTS` | Solo productos activos. Admite `categoryId` opcional y búsqueda por nombre mediante `search` sin distinguir mayúsculas de minúsculas; de manera predeterminada utiliza página 0, tamaño 20 y ordenación por `name`. Devuelve un objeto `Page` de Spring cuyo `content` incluye `id`, `name`, `description`, `price`, `active`, `stock`, `categoryName`. |
| `GET /api/products/{id}` | `READ_ONE_PRODUCT` | Devuelve el DTO de un producto activo o `404`. |
| `POST /api/products` | `SAVE_ONE_PRODUCT` | Requiere `name`, `description`, `price` positivo, `stock` no negativo y un `idCategory` existente; devuelve `201` y un mensaje de éxito. |
| `PUT /api/products/{id}` | `UPDATE_ONE_PRODUCT` | Usa los mismos campos de solicitud del producto; actualiza únicamente un producto activo y devuelve `200` y un mensaje de éxito. |
| `DELETE /api/products/{id}` | `DELETE_ONE_PRODUCT` | Realiza una eliminación lógica del producto activo estableciendo `active=false`; devuelve `204`. |
| `GET /api/categories` | `READ_ALL_CATEGORIES` | Devuelve DTO de categorías (`id`, `name`, `description`, `nameProducts`); el mapeador actual deja `nameProducts` sin establecer. |
| `POST /api/categories` | `SAVE_ONE_CATEGORY` | Requiere `name` y `description` no vacíos ni compuestos únicamente por espacios; devuelve `201`. |
| `PUT /api/categories/{id}` | `UPDATE_ONE_CATEGORY` | Reemplaza el nombre y la descripción; devuelve `200` o `404`. |
| `DELETE /api/categories/{id}` | `DELETE_ONE_CATEGORY` | Elimina físicamente una categoría existente y devuelve `204`; si no existe, devuelve `404`. El servicio no comprueba si hay productos que todavía la referencian y no dispone de un manejador específico para los errores de restricciones de persistencia que puedan producirse durante su eliminación. |

Aunque las reglas de seguridad por URL permiten las solicitudes `GET` al catálogo, los métodos del controlador también utilizan comprobaciones con `@PreAuthorize`. Por lo tanto, el comportamiento efectivo actual exige la autoridad indicada (ambos roles disponibles tienen permisos de lectura); las consultas anónimas del catálogo son rechazadas.

### Carritos y finalización de compra

| Método y ruta | Autoridad requerida | Contrato y resultado |
|---|---|---|
| `GET /api/cart` | `READ_ONE_CART` | Devuelve el carrito del usuario autenticado. Si no existe, lo crea dentro de la misma transacción. La respuesta incluye los artículos, el campo `priceAtPurchase` de cada artículo, subtotales, total y fecha de creación. |
| `POST /api/cart/create/{userId}` | `SAVE_ONE_CART` | Declara un cuerpo de solicitud `items` no vacío, pero no lo utiliza; crea un carrito vacío para el usuario indicado en la ruta, siempre que todavía no tenga uno. Este flujo del servicio no comprueba que el usuario indicado en la ruta coincida con el usuario autenticado. |
| `POST /api/cart/add/{userId}` | `ADD_ITEM_CART` | Cuerpo: `productId`, `quantity >= 1`. El servicio verifica que el usuario de la ruta sea el usuario autenticado. Incrementa la cantidad de un artículo coincidente o agrega uno nuevo, guardando el precio del producto en el momento de añadirlo. |
| `PUT /api/cart/item/{cartItemId}?quantity=n` | `UPDATE_QUANTITY_ITEM_CART` | `n` debe ser mayor que cero. El servicio verifica que el artículo del carrito pertenezca al usuario. |
| `DELETE /api/cart/item/{cartItemId}` | `DELETE_ITEM_CART` | Elimina un artículo del carrito perteneciente al usuario; devuelve `204`. |
| `DELETE /api/cart/clear` | `CLEAR_CART` | Vacía el carrito del usuario autenticado; devuelve `200`. |
| `DELETE /api/cart/clear/{userId}` | `CLEAR_CART` | Vacía el carrito del usuario indicado. A diferencia de las operaciones de agregar, actualizar o eliminar artículos, este flujo del servicio no comprueba la pertenencia del carrito; el acceso depende únicamente de la autoridad asociada al rol. |
| `POST /api/orders/checkout` | `PERFORM_CHECKOUT` | Convierte el carrito no vacío del usuario autenticado en un pedido y devuelve `201` con `OrderResponseDTO`. |
| `GET /api/orders/my-orders` | `READ_MY_ORDERS` | Devuelve los pedidos del usuario autenticado. |
| `GET /api/orders/admin/all` | `READ_ALL_ORDERS` | Devuelve una página con todos los pedidos; de manera predeterminada utiliza página 0, tamaño 20 y orden descendente por `id`. |
| `PUT /api/orders/{orderId}/status?status=value` | `UPDATE_ORDER_STATUS` | Acepta los valores del enum `CREATED`, `PAID`, `SHIPPED` o `CANCELED`, sin distinguir mayúsculas de minúsculas; devuelve `200` con el cuerpo vacío. |

### Rutas operativas y de documentación

| Ruta | Acceso | Comportamiento |
|---|---|---|
| `/swagger-ui/**`, `/v3/api-docs/**` | Público | Documentación OpenAPI interactiva y generada automáticamente |
| `GET /actuator/health` | Público | Endpoint de estado de salud; los detalles solo se muestran cuando existe autorización |
| `GET /actuator/prometheus` | Público | Endpoint de recopilación de métricas para Prometheus |
| Otras rutas `/actuator/**` | `ROLE_ADMINISTRATOR` | Endpoints de Actuator que no fueron declarados explícitamente públicos |

## Autenticación, autorización, CORS y cabeceras

### Roles y permisos

`USER` puede consultar productos y categorías, operar un carrito, finalizar compras y consultar sus propios pedidos. `ADMINISTRATOR` incluye todos los permisos de usuario más la administración de productos y categorías, la consulta de todos los pedidos y la actualización de sus estados. Las autoridades se generan dinámicamente a partir del enum `Role` del usuario almacenado en la base de datos; no se confía exclusivamente en las declaraciones del token.

La aplicación no mantiene estado de sesión (*stateless*) y tiene deshabilitada la protección CSRF. Los JWT solo se aceptan mediante una cabecera de autorización `Bearer `. La clave de firma se genera en memoria al iniciar la aplicación, por lo que los tokens emitidos antes de un reinicio dejan de ser válidos después de este.

### CORS

CORS está configurado para todas las rutas, con credenciales habilitadas, todas las cabeceras de solicitud y los métodos `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS` y `HEAD`, para los siguientes orígenes explícitos:

| Orígenes permitidos |
|---|
| `http://localhost:5173`, `http://127.0.0.1:5173` |
| `http://localhost:3000` |
| `http://localhost:8082`, `http://127.0.0.1:8082` |

La configuración de seguridad también permite todas las solicitudes `OPTIONS`.

### Cabeceras de seguridad de las respuestas

La cadena de seguridad configura HSTS (un año e inclusión de subdominios), una política CSP restrictiva (`default-src 'self'`; sin marcos ni objetos), la política de referencia `strict-origin-when-cross-origin` y una política de permisos que deshabilita geolocalización, micrófono y cámara.

## Modelo de dominio y relaciones

| Entidad | Campos principales | Relaciones |
|---|---|---|
| `User` | Nombre, correo único, contraseña con hash BCrypt, rol, dirección de envío, `createdAt` | Un carrito; muchos pedidos |
| `Category` | Nombre único, descripción | Uno a muchos productos |
| `Product` | Nombre, descripción, precio, stock, activo, `createdAt` | Muchos a una categoría; referenciado por artículos del carrito y de pedidos |
| `Cart` | `createdAt` | Uno a uno con usuario; uno a muchos artículos del carrito con cascada y eliminación de huérfanos |
| `CartItem` | Referencia al producto, cantidad, `priceAtPurchase` | Muchos a un carrito y a un producto |
| `Order` | Copia de la dirección de envío, ciudad, código postal, total, estado, `createdAt` | Muchos a un usuario; uno a muchos artículos del pedido con cascada y eliminación de huérfanos |
| `OrderItem` | Referencia al producto, precio, cantidad | Muchos a un pedido y a un producto |

Al finalizar la compra, los campos de envío del pedido se copian desde la dirección del usuario, conservando la dirección de entrega correspondiente a ese momento. Los productos se eliminan de forma lógica; los pedidos y sus artículos mantienen las referencias de clave foránea hacia los productos.

## Procesos críticos

### Catálogo

El listado crea una `Specification` de JPA que exige `active=true` y, opcionalmente, filtra por coincidencia exacta de `categoryId` y por una subcadena del nombre del producto, eliminando espacios sobrantes y convirtiendo el texto a minúsculas. Las operaciones de actualización y eliminación también buscan únicamente productos activos. La eliminación de categorías es una eliminación física mediante el repositorio, de modo que la integridad referencial de la base de datos constituye la última protección para las categorías con productos asociados.

### Carrito

Si se intenta consultar un carrito inexistente, este se crea automáticamente. Agregar un producto que ya está en el carrito incrementa su cantidad; un nuevo artículo almacena `Product.price` en `priceAtPurchase`. Los totales del carrito se calculan con ese precio almacenado en cada artículo y no con el precio actual del producto. Las modificaciones del carrito son transaccionales.

### Finalización de compra y pedidos

La finalización de compra (*checkout*) es transaccional. El proceso carga el carrito del usuario que realiza la solicitud, rechaza un carrito vacío, guarda una copia de la dirección de envío, comprueba el stock de cada artículo, descuenta y guarda las existencias de cada producto, crea los artículos del pedido, calcula el total, guarda el pedido y, finalmente, vacía el carrito. Si falla la verificación de stock, se revierte toda la transacción.

Detalle observado sobre los precios: al finalizar la compra, cada `OrderItem.price` se establece a partir del precio actual del producto y no del valor `priceAtPurchase` almacenado en el carrito. Por lo tanto, el total final del pedido se calcula con el precio vigente al confirmar la compra, mientras que el total del carrito utiliza el precio del momento en que se agregó el artículo.

La transacción es atómica, pero no incorpora bloqueos pesimistas, un campo `@Version` para control de versiones optimista ni una clave de idempotencia. El proceso de compra carga y guarda los productos mediante los métodos habituales del repositorio, sin un identificador de solicitud ni una búsqueda de pedidos duplicados. En consecuencia, la implementación no ofrece garantías de concurrencia o reintentos/idempotencia a nivel de aplicación más allá de la transacción de base de datos; la batería de pruebas inspeccionada no evalúa compras simultáneas.

### Administración

Las autoridades de administrador permiten crear y modificar productos y categorías, paginar la totalidad de los pedidos y cambiar sus estados. La interpretación del estado utiliza `OrderStatus.valueOf(status.toUpperCase())`; los valores inválidos generan `IllegalArgumentException`, que no tiene un mapeo específico en el manejador global de errores.

## Errores y validación

Bean Validation se aplica a los cuerpos de solicitud marcados con `@Valid`. Una excepción `MethodArgumentNotValidException` devuelve `400` y un objeto JSON que relaciona los nombres de los campos inválidos con sus mensajes, por ejemplo:

```json
{ "price": "Price must be positive" }
```

| Condición | Mapeo de respuesta observado |
|---|---|
| No se encuentra un producto, categoría, usuario, carrito o pedido del dominio | `404` con un mensaje de texto plano para la excepción correspondiente que cuenta con manejador |
| Carrito vacío o stock insuficiente | `400` con mensaje de texto plano cuando se utiliza la excepción específica |
| Ya existe un carrito al intentar crearlo manualmente | `400` con mensaje de texto plano |
| Cantidad inválida de un artículo del carrito en el servicio | `404` porque `QuantityException` se mapea a `NOT_FOUND` |
| Falta de autoridad o solicitud anónima a una ruta protegida | Gestionado por Spring Security; generalmente `403` en las pruebas actuales con MockMvc |
| Registro duplicado, estado de pedido inválido, incumplimiento de restricciones de persistencia y otros errores de ejecución no controlados | Sin mapeo global específico; se aplica el manejo de errores predeterminado de Spring Boot |

Actualmente, el proceso de compra lanza `CartNotFoundException` cuando el carrito existe, pero está vacío. Por eso, esa situación particular se representa con `404`, a pesar de que existe un manejador independiente para `CartEmptyException`.

## Persistencia, esquema, datos iniciales y migraciones

Hibernate crea o actualiza el esquema al iniciar la aplicación (`spring.jpa.hibernate.ddl-auto=update`) sobre PostgreSQL. El archivo `src/main/resources/import.sql` está configurado como script de carga de datos y, de forma predeterminada, se ejecuta con `SQL_INIT_MODE=always`; inserta usuarios, categorías, productos, carritos, artículos del carrito, un pedido y artículos del pedido de ejemplo mediante instrucciones SQL de PostgreSQL tolerantes a conflictos.

En el backend inspeccionado no existen dependencias de Flyway ni Liquibase, directorios de migraciones ni configuración de migraciones versionadas. `infrastructure/scripts/schema-actual.sql` es un volcado (*dump*) de PostgreSQL 15 y no una migración de la aplicación. Registra claves primarias, claves únicas y claves foráneas de las siete tablas del dominio. Como representa una instantánea del esquema, debe considerarse descriptivo y no la fuente principal para inicializar la aplicación: Hibernate modifica el esquema en tiempo de ejecución e `import.sql` carga los datos iniciales.

El volcado incluido en el repositorio exige que el stock de un producto sea al menos 1, mientras que `ProductRequestDTO` acepta 0. Esta discrepancia puede manifestarse si dicho volcado representa la base de datos de destino y se intenta crear un producto sin stock.

## Configuración y ejecución

| Configuración | Valor predeterminado / uso |
|---|---|
| `DB_NAME` | URL JDBC de PostgreSQL para `easyecommerce` en el puerto local 5432, con opción UTC |
| `DB_USER` | Usuario de base de datos, `postgres` de manera predeterminada |
| `DB_PASSWORD` | Contraseña de la base de datos; debe proporcionarse un secreto específico del entorno de despliegue |
| `PORT` | Puerto HTTP, `8081` de manera predeterminada |
| `SQL_INIT_MODE` | Modo de inicialización SQL, `always` de manera predeterminada |
| `security.jwt.expiration-minutes` | 30 minutos en la configuración de la aplicación |

El Dockerfile de la raíz compila la aplicación con Maven/Temurin 25 y ejecuta el archivo JAR generado sobre Temurin 25 JRE. El archivo Compose define PostgreSQL 15, el backend, un proxy para el frontend, PgAdmin, Prometheus/Grafana y otros servicios operativos. El backend permanece dentro de la red interna de Compose; el frontend se publica en el host `127.0.0.1:8082`.

Comandos útiles:

```bash
# Pruebas del backend
./mvnw test

# Ejecución directa en desarrollo
./mvnw spring-boot:run

# Despliegue con Compose
docker compose -f infrastructure/docker-compose.yml up --build
```

En Windows PowerShell, utilizar `./mvnw.cmd` para los comandos de Maven Wrapper. No subir credenciales reales al repositorio; utilizar el mecanismo de variables de entorno disponible y los secretos correspondientes al despliegue.

## Pruebas y cobertura verificada

La batería de pruebas utiliza `@SpringBootTest` junto con MockMvc. Verifica el inicio del contexto de Spring, registro/inicio de sesión/`auth-me`, solicitudes CORS previas (*preflight*) y cabeceras del inicio de sesión, flujos HTTP de productos/categorías/carrito, casos de autorización, determinadas comprobaciones de pertenencia de carritos, contratos del controlador de pedidos con un servicio simulado (*mock*) y reglas de seguridad para Actuator y las cabeceras. La configuración de pruebas emplea H2 en modo de compatibilidad con PostgreSQL, crea y elimina el esquema y habilita la inicialización SQL.

Al preparar este documento se ejecutó `./mvnw.cmd -B test`: **45 pruebas aprobadas, 0 fallos, 0 errores y 0 omitidas**. Esto valida la batería de pruebas respaldada por H2, pero no un despliegue real sobre PostgreSQL ni el comportamiento de compras simultáneas.

## Limitaciones observadas y advertencias sobre los contratos

- El README del repositorio y algunas descripciones OpenAPI de los controladores están desactualizados respecto del código. En particular, las rutas actuales incluyen `/api` y las lecturas de productos/categorías están protegidas mediante autorización.
- La clave de firma JWT almacenada en memoria cambia cada vez que se inicia el proceso, por lo que los tokens emitidos anteriormente quedan invalidados después de un reinicio.
- El proceso de compra no implementa un bloqueo pesimista explícito de productos, un campo de versión optimista ni un mecanismo de idempotencia; las pruebas inspeccionadas no cubren compras simultáneas ni reintentos.
- La eliminación de categorías con productos asociados depende de que la base de datos rechace la operación por restricciones de integridad y no cuenta con una respuesta específica de conflicto.
- `POST /api/cart/create/{userId}` valida un cuerpo de solicitud que posteriormente no utiliza.
- `POST /api/cart/create/{userId}` no realiza una comprobación de pertenencia del usuario indicado en la ruta a nivel de servicio.
- `DELETE /api/cart/clear/{userId}` no realiza una comprobación de pertenencia a nivel de servicio, a diferencia de los otros métodos de modificación de carritos que reciben un ID en la ruta.
- Las pruebas incluidas se ejecutan con H2, mientras que la aplicación en tiempo de ejecución utiliza PostgreSQL; el comportamiento específico del esquema y del dialecto en producción debe verificarse por separado.

