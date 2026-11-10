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

**3. Levantar todo**

```bash
docker compose up -d --build
```

La primera vez tarda alrededor de un minuto en construir la imagen. Levanta, en orden:

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

A los pocos segundos aparecen líneas como esta (el envío por WhatsApp está simulado con un
log, y el teléfono se muestra enmascarado):

```
INFO app.jobs.notifier: To +549…0301: Alerta de helada en Lote Norte: 63% de probabilidad para el 14/11.
```

**6. Usar la API**

Abrí http://localhost:8000: redirige a la documentación interactiva (`/docs`). Tocá
**Authorize**, ingresá `ana@example.com` como username y `demo-password` como password, y
probá los endpoints desde el navegador.

Cuentas de demo (todas con la contraseña `demo-password`):

| Usuario | Rol | Login |
|---|---|---|
| Admin | admin | `admin@example.com` o `+5493410000100` |
| Técnico | technician | `tecnico@example.com` o `+5493410000200` |
| Ana Pérez | client | `ana@example.com` o `+5493415550301` |
| Juan Gómez | client | `juan@example.com` o `+5493415550402` |

El paso a paso para recorrer todo lo que hace el sistema está en
**[docs/demo.md](docs/demo.md)**.

**7. Apagar**

```bash
docker compose down        # apaga y conserva los datos
docker compose down -v     # apaga y borra la base (la próxima vez arranca de cero)
```

### Correr los tests

Los tests corren contra un Postgres real. Hace falta [uv](https://docs.astral.sh/uv/):

```bash
docker compose up -d db
uv sync
uv run pytest
```

Si cambiaste `DB_PORT`, indicá la base de test, por ejemplo:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://weather:weather@localhost:5433/weather_test uv run pytest
```

Lint: `uv run ruff check . && uv run ruff format --check .`. El CI de GitHub corre lint,
tests y el build de la imagen en cada push.

## Cómo funciona

```mermaid
flowchart LR
    CLIENT([Web o bot de WhatsApp]) -->|Bearer token| API[API FastAPI]
    API --> DB[(PostgreSQL)]
    ING[Ingesta meteorológica<br/>existente · acá simulada] -->|upsert de pronósticos| DB
    WORKER[Worker] -->|evalúa y encola avisos| DB
    WORKER -->|envía| NOTIFIER[Notifier<br/>hoy: log]
```

- Una **organización** (un establecimiento) tiene **puntos de medición**; un usuario también
  puede tener puntos propios. Los usuarios de una organización ven todos sus puntos.
- La ingesta escribe, para cada punto, la **probabilidad** de cada evento (helada, lluvia,
  granizo, viento fuerte, ola de calor) para los próximos días.
- Cada usuario crea **alertas** sobre los puntos que ve: un evento y un umbral.
- El **worker** corre en loop. En cada ciclo:
  1. **Evalúa**: una sola consulta SQL encuentra las alertas superadas y deja los avisos
     pendientes.
  2. **Envía** los pendientes, de a uno, y los marca enviados, fallidos o descartados.
- Se vuelve a avisar si la probabilidad sigue subiendo (15 puntos o más sobre el último
  aviso de ese día).
- Hay tres roles: **cliente** (consulta y maneja sus alertas), **técnico** (gestiona
  organizaciones, puntos y estados) y **admin** (además borra y cambia roles).
- Un punto puede estar **en testing** (instalándose o calibrándose): sus datos no se
  muestran a los clientes y no disparan alertas.

El modelo de datos completo y las reglas están en [docs/design.md](docs/design.md).

## Decisiones

**Modelo de datos**

- **Las reglas de integridad viven en la base**, no solo en Python: uniques, checks
  (umbral 1–100, probabilidad 0–100, teléfono E.164, exactamente un dueño por punto), FKs con
  borrado en cascada y triggers. Así se cumplen aunque escriba un sistema externo como la
  ingesta, y aunque haya concurrencia.
- **Probabilidad y umbral como enteros de 0 a 100**: sin problemas de decimales y es como lo
  lee un usuario.
- **El pronóstico se guarda por punto de medición**, que tiene coordenadas. La ingesta lee
  los puntos y escribe sus pronósticos; nuestro código solo los lee.
- **Las alertas son de cada usuario**, aunque el punto sea compartido: cada uno elige qué
  quiere recibir y el aviso le llega a quien la creó.
- **Los avisos son a la vez historial y cola de envío** (patrón *outbox*): el evaluador los
  deja pendientes y otro paso los envía. Así se puede reintentar un envío sin volver a
  evaluar.

**Evaluación**

- **Una sola consulta SQL** (`INSERT ... SELECT ... ON CONFLICT DO NOTHING`) hace el cruce
  completo dentro de Postgres: no viajan filas a Python.
- **Es idempotente**: `UNIQUE(alerta, día, probabilidad)` hace que correrla dos veces no
  duplique avisos. Además, un **advisory lock** de Postgres hace que dos workers no evalúen
  a la vez: sin él, con datos que cambian entre dos corridas, podían salir dos avisos por la
  misma subida.
- **Está escrita en SQL y no con el query builder de SQLAlchemy** porque se lee como la
  consulta que corre. La versión con el query builder está en `app/jobs/evaluator_core.py`
  como alternativa, y los tests corren contra las dos.
- **"Hoy" se calcula en la zona horaria configurada**, no en UTC: a las 22 h de Argentina, en
  UTC ya es mañana.

**Envío**

- **`FOR UPDATE SKIP LOCKED`**: varios workers se reparten la cola sin esperarse.
- **Un aviso por transacción, con timeout de 10 s**: si el proceso muere, como mucho se
  repite un mensaje (entrega *at-least-once*), y un proveedor colgado no traba el worker.
- **Reintentos con espera creciente** (1, 2, 4 y 8 minutos): una caída corta de WhatsApp no
  pierde avisos. Después de 5 intentos el aviso queda fallido, y uno fallido no cuenta como
  "ya avisado".
- **Antes de enviar se revisa que el aviso siga correspondiendo**: si la alerta se pausó, el
  punto pasó a testing, el usuario dejó la organización o el día ya pasó, se descarta.

**Worker**

- **Proceso separado de la API**, con un loop asyncio y sin Celery ni Redis: alcanza para el
  volumen del problema y se escala aparte. Se apaga limpio con SIGTERM, entre un aviso y el
  siguiente.
- **El intervalo debería seguir a la frecuencia de la ingesta.** El valor por defecto es
  60 s; en la demo, worker e ingesta simulada comparten 10 s para ver avisos rápido.

**Estados de puntos y pronósticos**

- **Cada lectura nueva toma el estado actual del punto**, y **lo recibido durante el testing
  sigue siendo dato de prueba**: si un sensor en calibración manda granizo al 100%, ese
  valor no dispara alertas cuando el punto pasa a activo. La regla está en un trigger de
  Postgres porque la ingesta es un sistema externo que no pasa por nuestro código.

**API y autenticación**

- **Login con email (web) o teléfono (WhatsApp)** y contraseña; devuelve un token JWT. Las
  contraseñas se guardan con argon2, que se calcula en un thread aparte para no bloquear el
  event loop.
- **Roles globales y acumulativos**, chequeados con una dependencia de FastAPI.
- **Las reglas de visibilidad están en un solo módulo** (`app/access.py`), y el evaluador y el
  dispatcher aplican la misma regla.
- **Lo que un usuario no puede ver responde 404, no 403**, para no revelar qué ids existen.
- **Duplicados y referencias los valida la base**: un error de integridad se traduce a 409
  (duplicado) o 422. Chequear antes de insertar tendría una carrera de todas formas.
- **Todo el I/O es async**, de la API al worker.

**Tests**

- **Contra Postgres real**, no SQLite: el sistema depende de enums, triggers,
  `ON CONFLICT`, `SKIP LOCKED` y advisory locks. Cada test corre en una transacción que se
  descarta. Detalle en [docs/tests.md](docs/tests.md).

## Qué faltó y mejoras posibles

**Fuera de alcance por el enunciado**

- **La integración real con WhatsApp.** El envío pasa por una interfaz `Notifier`; hoy la
  implementa `LogNotifier`, y WhatsApp sería otra clase con el mismo método.
- **La ingesta**, que el enunciado da por existente: acá está simulada en `app/mocks/`.

**Limitaciones conocidas**

- **Un aviso fallido no se vuelve a encolar si la probabilidad no cambia**, porque el
  unique de alerta, día y probabilidad lo impide. Si cambia, sí.
- **El registro con un email o teléfono ya usado responde 409**, lo que deja ver qué cuentas
  existen. Es la práctica habitual, pero vale la pena saberlo.
- **No hay límite de intentos de login** en la app; iría en el proxy o en el balanceador.
- **El secreto JWT por defecto del compose es solo para correrlo local.** Cualquier
  despliegue real necesita su propio `JWT_SECRET`, largo y aleatorio.
- **Una sola zona horaria para todos los puntos.**
- **Los nombres de organización se pueden repetir**: dos establecimientos pueden llamarse
  igual.
- **`GET /notifications` devuelve el id de la alerta**, sin el punto ni el evento.

**Mejoras posibles**

- **Permisos por organización y por punto**, en lugar de roles globales (por ejemplo, admin
  de su establecimiento y cliente en otro).
- **Evaluar apenas la ingesta escribe** (`LISTEN/NOTIFY` de Postgres) en vez de cada X
  segundos.
- **Avisar cuando la probabilidad baja** ("ya no se espera helada").
- **Refresh tokens, recuperación de contraseña y verificación de email y teléfono.**
- **Mediciones de sensores.** El enunciado define la ingesta como probabilidades de eventos
  por día, y así se modeló. Un sistema real con estaciones probablemente guardaría también
  mediciones (temperatura, humedad, lluvia caída) y derivaría los eventos de ahí.
- **Historial de quién cambió el estado de un punto o de un pronóstico.**
