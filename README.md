# weather-alerts

Sistema de alertas climáticas para establecimientos agropecuarios. Los usuarios configuran
alertas sobre sus puntos de medición (por ejemplo, "avisame si la probabilidad de helada en
el Lote Norte llega al 60%") y un proceso en background cruza esas alertas con los
pronósticos que ya guarda el sistema de ingesta y avisa cuando se supera el umbral.

FastAPI, SQLAlchemy 2 async con asyncpg, PostgreSQL 16 y Alembic.

- [Cómo correrlo](#cómo-correrlo)
- [Cómo funciona](#cómo-funciona)
- [Decisiones](#decisiones)
- [Qué faltó y mejoras posibles](#qué-faltó-y-mejoras-posibles)
- Más detalle: [recorrido de la demo](docs/demo.md), [diseño](docs/design.md),
  [qué está testeado](docs/tests.md)

## Cómo correrlo

Solo hace falta **Docker** con **Docker Compose v2** (el comando `docker compose`).

**1. Clonar el repo**

```bash
git clone https://github.com/MolinaFranco/weather-alerts.git
cd weather-alerts
```

**2. (Opcional) Cambiar los puertos**

La API usa el puerto 8000 y Postgres el 5432. Si alguno está ocupado en tu máquina:

```bash
cp .env.example .env
# editá API_PORT y/o DB_PORT en .env, por ejemplo API_PORT=8001
```

Si ya tenés otra copia de este proyecto corriendo, agregá `-p otro-nombre` a cada comando de
`docker compose` para que no se pisen.

**3. Levantar todo**

```bash
docker compose up -d --build
```

La primera vez tarda menos de un minuto en construir la imagen. Levanta:

| Servicio | Qué hace |
|---|---|
| `db` | Postgres |
| `migrate` | Corre las migraciones y termina |
| `seed` | Carga los datos de demo y termina |
| `api` | La API en `http://localhost:8000` |
| `fake_ingest` | Simula la ingesta meteorológica: cada 10 s actualiza pronósticos |
| `worker` | Cada 10 s evalúa las alertas y envía los avisos |

**4. Verificar que esté todo arriba**

```bash
docker compose ps -a
```

`migrate` y `seed` tienen que figurar como `Exited (0)`; los demás, `Up`.

**5. Ver los avisos**

```bash
docker compose logs -f worker
```

A los pocos segundos aparecen líneas como esta. El envío por WhatsApp está simulado con un
log, y el teléfono se muestra enmascarado:

```
INFO app.jobs.notifier: To +549…0402: Alerta de helada en Lote Norte: 43% de probabilidad para el 14/11.
```

**6. Usar la API**

Abrí http://localhost:8000: redirige a la documentación interactiva (`/docs`). Tocá
**Authorize**, ingresá `ana@example.com` como username y `demo-password` como password, y
probá los endpoints desde el navegador.

Cuentas de demo, todas con la contraseña `demo-password`:

| Usuario | Rol | Login |
|---|---|---|
| Admin | admin | `admin@example.com` o `+5493410000100` |
| Técnico | technician | `tecnico@example.com` o `+5493410000200` |
| Ana Pérez | client | `ana@example.com` o `+5493415550301` |
| Juan Gómez | client | `juan@example.com` o `+5493415550402` |

Para crear un admin propio:

```bash
docker compose exec api python -m app.create_admin "Tu nombre" vos@example.com +5493410000999
```

El paso a paso para recorrer todo lo que hace el sistema está en
**[docs/demo.md](docs/demo.md)**.

**7. Apagar**

```bash
docker compose down        # apaga y conserva los datos
docker compose down -v     # apaga y borra la base (la próxima vez arranca de cero)
```

### Correr los tests

Los tests corren contra un Postgres real, en una base aparte (`weather_test`) que crea el
compose. Hace falta [uv](https://docs.astral.sh/uv/):

```bash
docker compose up -d db
uv sync
TEST_DATABASE_URL=postgresql+asyncpg://weather:weather@localhost:5432/weather_test uv run pytest
```

Si cambiaste `DB_PORT`, usá ese puerto en lugar de 5432. Lint:
`uv run ruff check . && uv run ruff format --check .`. El CI de GitHub corre lint, tests y
el build de la imagen en cada push.

### Correrlo sin Docker

Con Postgres en Docker y el resto local, útil para desarrollar:

```bash
cp .env.example .env                    # DATABASE_URL apunta a localhost
docker compose up -d db
uv sync
uv run alembic upgrade head             # migraciones
uv run python -m app.mocks.seed         # datos de demo
uv run uvicorn app.main:app --reload    # API
uv run python -m app.worker             # en otra terminal
uv run python -m app.mocks.fake_ingest  # en otra terminal
```

### Configuración

Todo se configura con variables de entorno (o el archivo `.env`):

| Variable | Por defecto | Qué es |
|---|---|---|
| `DATABASE_URL` | (obligatoria) | Conexión a Postgres, con el driver `postgresql+asyncpg://` |
| `JWT_SECRET` | (obligatoria, 32 caracteres o más) | Firma los tokens de login |
| `ACCESS_TOKEN_MINUTES` | `60` | Cuánto dura un token |
| `CORS_ORIGINS` | `[]` | Orígenes de navegador habilitados, por ejemplo `["https://app.example.com"]` |
| `TIMEZONE` | `America/Argentina/Buenos_Aires` | Zona horaria para decidir qué día es hoy |
| `RENOTIFY_STEP` | `15` | Puntos que tiene que subir la probabilidad para volver a avisar |
| `EVALUATION_INTERVAL` | `60` | Segundos entre ciclos del worker (en la demo, 10) |
| `INGEST_INTERVAL` | `10` | Segundos entre pasadas de la ingesta simulada |
| `API_PORT`, `DB_PORT` | `8000`, `5432` | Puertos del compose en tu máquina |

## Cómo funciona

```mermaid
flowchart LR
    CLIENT([Web o bot de WhatsApp]) -->|Bearer token| API[API FastAPI]
    API --> DB[(PostgreSQL)]
    ING[Ingesta meteorológica<br/>existente · acá simulada] -->|upsert de pronósticos| DB
    WORKER[Worker] -->|evalúa y encola avisos| DB
    WORKER -->|envía| NOTIFIER[Notifier<br/>hoy: log]
```

- Una organización (un establecimiento) tiene puntos de medición, y un usuario también puede
  tener puntos propios. Los usuarios de una organización ven todos sus puntos.
- La ingesta escribe, para cada punto, la probabilidad de cada evento (helada, lluvia,
  granizo, viento fuerte, ola de calor) para los próximos días.
- Cada usuario crea alertas sobre los puntos que ve: un evento y un umbral.
- El worker corre en loop. En cada ciclo primero evalúa (una sola consulta SQL encuentra las
  alertas superadas y deja los avisos pendientes) y después envía los pendientes, de a uno.
- Si la probabilidad sigue subiendo, se vuelve a avisar cuando sube 15 puntos o más sobre el
  último aviso de ese día.
- Hay tres roles: cliente (consulta y maneja sus alertas), técnico (además gestiona
  usuarios, organizaciones, puntos y estados) y admin (además borra y cambia roles).
- Un punto puede estar en testing mientras se instala o calibra: sus datos no se muestran a
  los clientes y no disparan alertas.

El modelo de datos completo y las reglas están en [docs/design.md](docs/design.md).

## Decisiones

### Modelo de datos

Las reglas de integridad viven en la base y no solo en Python: uniques, checks (umbral de 1 a
100, probabilidad de 0 a 100, teléfono E.164, exactamente un dueño por punto), FKs con borrado
en cascada y triggers. Así se cumplen aunque escriba un sistema externo como la ingesta, y
aunque haya concurrencia.

La probabilidad y el umbral son enteros de 0 a 100: sin problemas de decimales, y es como lo
lee un usuario. El pronóstico se guarda por punto de medición, que tiene coordenadas; la
ingesta lee los puntos y escribe sus pronósticos, y nuestro código solo los lee.

Las alertas son de cada usuario aunque el punto sea compartido, así cada uno elige qué quiere
recibir. Los avisos son a la vez historial y cola de envío (el patrón *outbox*): el evaluador
los deja pendientes y otro paso los envía, lo que permite reintentar un envío sin volver a
evaluar.

### Evaluación

La evaluación es una sola consulta SQL (`INSERT ... SELECT ... ON CONFLICT DO NOTHING`) que
hace el cruce completo dentro de Postgres, sin traer filas a Python. Es idempotente:
`UNIQUE(alerta, día, probabilidad)` hace que correrla dos veces no duplique avisos. Además, un
advisory lock de Postgres impide que dos workers evalúen a la vez; sin él, con datos que
cambian entre dos corridas, podían salir dos avisos por la misma subida.

Está escrita en SQL porque así se lee como la consulta que corre.
`app/jobs/evaluator_query_builder.py` tiene la misma consulta armada con el query builder de
SQLAlchemy, para comparar las dos formas: gana validación al importar y autocompletado, y
pierde legibilidad. El worker usa la de SQL, y los tests corren contra las dos.

"Hoy" se calcula en la zona horaria configurada y no en UTC: a las 22 h de Argentina, en UTC
ya es mañana.

### Envío

Los avisos se toman con `FOR UPDATE SKIP LOCKED`, así varios workers se reparten la cola sin
esperarse. Cada aviso se envía en su propia transacción y con un timeout de 10 s: si el
proceso muere, como mucho se repite un mensaje (entrega *at-least-once*), y un proveedor
colgado no traba el worker.

Un envío fallido se reintenta con esperas de 1, 2, 4, 8 y 16 minutos y después cada media
hora, mientras el aviso siga correspondiendo: aunque WhatsApp esté caído un buen rato, el aviso
llega cuando vuelve. Recién cuando pasa el día del pronóstico se descarta.
Antes de enviar se revisa que el aviso siga correspondiendo: si la alerta se pausó, el punto
pasó a testing, el usuario dejó la organización o el día ya pasó, se descarta.

### Worker

Es un proceso separado de la API, con un loop asyncio, sin Celery ni Redis: alcanza para el
volumen del problema y se escala aparte. Se apaga limpio con SIGTERM, entre un aviso y el
siguiente. El intervalo debería seguir la frecuencia de la ingesta: por defecto es de 60 s, y
en la demo el worker y la ingesta simulada comparten 10 s para ver avisos rápido.

### Estados de puntos y pronósticos

Cada lectura nueva toma el estado actual del punto, y lo recibido durante el testing sigue
siendo dato de prueba: si un sensor en calibración manda granizo al 100%, ese valor no dispara
alertas cuando el punto pasa a activo. La regla está en un trigger de Postgres porque la
ingesta es un sistema externo que no pasa por nuestro código.

### API y autenticación

El login acepta email (pensado para una web) o teléfono (para el bot de WhatsApp) y devuelve un
token JWT. Las contraseñas se guardan con argon2, que se calcula en un thread aparte para no
bloquear el event loop. Los roles son globales y acumulativos, y se chequean con una
dependencia de FastAPI.

Qué ve cada usuario está definido en `app/access.py`. El evaluador y el dispatcher repiten la
misma regla en su propia consulta, y hay tests que verifican que un usuario que deja una
organización deja de recibir avisos de sus puntos. Lo que alguien no puede ver responde 404 y
no 403, para no revelar qué ids existen.

Los duplicados y las referencias los valida la base: un error de integridad se traduce a 409
(duplicado) o 422 (algo que no existe). Chequear antes de insertar tendría una carrera de todas
formas. Todo el I/O es async, de la API al worker.

### Tests

Corren contra Postgres real y no contra SQLite, porque el sistema depende de enums, triggers,
`ON CONFLICT`, `SKIP LOCKED` y advisory locks. Cada test corre en una transacción que se
descarta. El detalle está en [docs/tests.md](docs/tests.md).

## Qué faltó y mejoras posibles

### Fuera de alcance por el enunciado

- La integración real con WhatsApp. El envío pasa por una interfaz `Notifier`; hoy la
  implementa `LogNotifier`, y WhatsApp sería otra clase con el mismo método.
- La ingesta, que el enunciado da por existente. Acá está simulada en `app/mocks/`.

### Limitaciones que encontré

- Un envío que falla siempre (por ejemplo, un teléfono que no existe) se reintenta hasta que
  pasa el día del pronóstico. Con un proveedor real habría que distinguir los errores
  permanentes y marcarlos como fallidos enseguida.
- El registro con un email o teléfono ya usado responde 409, lo que deja ver qué cuentas
  existen.
- No hay límite de intentos de login en la app; iría en el proxy o en el balanceador.
- El secreto JWT y las credenciales de Postgres del compose son para correrlo local.
  Cualquier despliegue real necesita los suyos.
- Hay una sola zona horaria para todos los puntos.
- Los nombres de organización se pueden repetir: dos establecimientos pueden llamarse igual.
- `GET /notifications` devuelve el id de la alerta, sin el punto ni el evento.
- Solo los avisos están paginados; los demás listados devuelven todo.
- No se borran avisos ni pronósticos viejos.
- El worker no tiene un chequeo de salud propio; solo la API tiene `/health`.
- Los logs son texto plano y no hay métricas.

### Mejoras posibles

- Permisos por organización y por punto, en lugar de roles globales (por ejemplo, admin de su
  establecimiento y cliente en otro).
- Evaluar apenas la ingesta escribe, con `LISTEN/NOTIFY` de Postgres, en vez de cada X
  segundos.
- Avisar cuando la probabilidad baja ("ya no se espera helada").
- Refresh tokens, recuperación de contraseña y verificación de email y teléfono.
- Mediciones de sensores. El enunciado define la ingesta como probabilidades de eventos por
  día, y así se modeló. Un sistema real con estaciones probablemente guardaría también
  mediciones (temperatura, humedad, lluvia caída) y derivaría los eventos de ahí.
- Un historial de quién cambió el estado de un punto o de un pronóstico.
