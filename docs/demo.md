# Recorrido de la demo

Una guía para ver funcionar todo el sistema, paso a paso. Los ejemplos usan la API en
`http://localhost:8000`; si cambiaste `API_PORT`, usá ese puerto.

1. [Levantar la demo](#1-levantar-la-demo)
2. [Qué datos trae](#2-qué-datos-trae)
3. [Ver los avisos en vivo](#3-ver-los-avisos-en-vivo)
4. [Entrar como cliente](#4-entrar-como-cliente-ana)
5. [Lo que un cliente no puede hacer](#5-lo-que-un-cliente-no-puede-hacer)
6. [Activar un punto en testing](#6-activar-un-punto-en-testing-como-técnico)
7. [Marcar un pronóstico anómalo](#7-marcar-un-pronóstico-anómalo)
8. [Administrar usuarios](#8-administrar-usuarios-como-admin)
9. [Lo mismo con curl](#9-lo-mismo-con-curl)
10. [Mirar la base de datos](#10-mirar-la-base-de-datos)
11. [Salud del servicio](#11-salud-del-servicio)
12. [Volver a empezar](#12-volver-a-empezar)
13. [Si algo no anda](#13-si-algo-no-anda)

## 1. Levantar la demo

```bash
docker compose up -d --build
docker compose ps -a
```

Esperá a que `migrate` y `seed` figuren como `Exited (0)` y el resto como `Up`. Desde ese
momento, la ingesta simulada escribe pronósticos cada 10 segundos y el worker evalúa y
envía avisos cada 10 segundos.

## 2. Qué datos trae

Todas las cuentas usan la contraseña `demo-password`.

| id | Usuario | Rol | Email | Teléfono |
|---|---|---|---|---|
| 1 | Admin | admin | `admin@example.com` | `+5493410000100` |
| 2 | Técnico | technician | `tecnico@example.com` | `+5493410000200` |
| 3 | Ana Pérez | client | `ana@example.com` | `+5493415550301` |
| 4 | Juan Gómez | client | `juan@example.com` | `+5493415550402` |

Ana y Juan son miembros de la organización **Estancia La Esperanza** (id 1).

| id | Punto | De quién | Estado |
|---|---|---|---|
| 1 | Lote Norte | Estancia La Esperanza | active |
| 2 | Lote Sur | Estancia La Esperanza | active |
| 3 | Potrero Nuevo | Estancia La Esperanza | **testing** |
| 4 | Quinta de Juan | Juan (punto particular) | active |

| id | Alerta | Qué muestra |
|---|---|---|
| 1 | Ana · helada ≥ 60% · Lote Norte | una alerta sobre un punto compartido |
| 2 | Ana · lluvia ≥ 70% · Lote Sur | un umbral alto, que avisa poco |
| 3 | Ana · lluvia ≥ 50% · Potrero Nuevo | no avisa mientras el punto esté en testing |
| 4 | Juan · helada ≥ 40% · Lote Norte | otro miembro sobre el mismo punto |
| 5 | Juan · granizo ≥ 50% · Quinta de Juan | un punto particular |
| 6 | Técnico · viento fuerte ≥ 45% · Quinta de Juan | el staff recibe avisos de cualquier punto |

## 3. Ver los avisos en vivo

```bash
docker compose logs -f worker
```

Cada aviso es una línea así:

```
INFO app.jobs.notifier: To +549…0301: Alerta de helada en Lote Norte: 63% de probabilidad para el 14/11.
```

- El envío por WhatsApp está simulado: el aviso se escribe en el log.
- El teléfono se muestra enmascarado; los últimos cuatro dígitos dicen a quién fue:
  `…0301` es Ana, `…0402` es Juan y `…0200` es el técnico.
- Después de un ciclo con actividad aparece `Cycle done: N notices queued, M handled`.

**Re-notificación.** Si la probabilidad de un día sigue subiendo, se vuelve a avisar cuando
supera en 15 puntos o más al último aviso. Después de un par de minutos se ven cadenas como
`granizo en Lote Sur: 39%` y más tarde `55%` para el mismo día. Para listarlas, ver
[la sección 10](#10-mirar-la-base-de-datos).

La alerta de Ana sobre **Potrero Nuevo** no aparece nunca en los logs: el punto está en
testing.

## 4. Entrar como cliente (Ana)

1. Abrí http://localhost:8000 (redirige a `/docs`).
2. Arriba a la derecha, **Authorize**. En `username` poné `ana@example.com` (o su teléfono,
   `+5493415550301`), en `password` poné `demo-password`, y **Authorize**. Los campos
   `client_id` y `client_secret` quedan vacíos.
3. Probá, con **Try it out** y **Execute**:

| Endpoint | Qué esperar |
|---|---|
| `GET /me` | Ana, rol `client`, organización Estancia La Esperanza |
| `GET /points` | Solo **Lote Norte** y **Lote Sur**. No ve Potrero Nuevo (testing) ni la Quinta de Juan |
| `GET /points/{point_id}/forecasts` con `point_id` = 1 | Los pronósticos de los próximos 7 días, por día y evento. Probá también `since` y `until` (formato `2026-11-12`) |
| `GET /alerts` | Sus tres alertas (1, 2 y 3) |
| `POST /alerts` | Crear una alerta nueva, por ejemplo `{"point_id": 2, "event_type": "hail", "threshold": 30}`. Responde `201`, y en unos ciclos empieza a aparecer en los logs |
| `GET /notifications` | Sus avisos, más nuevos primero. `limit` y `offset` para paginar |

Para cambiar de usuario: **Authorize** → **Logout** y volver a entrar con otra cuenta.

## 5. Lo que un cliente no puede hacer

Siguiendo como Ana:

| Intento | Respuesta | Por qué |
|---|---|---|
| `POST /alerts` repitiendo `{"point_id": 2, "event_type": "hail", "threshold": 30}` | `409` | Ya tiene una alerta de granizo en ese punto |
| `POST /alerts` con `"threshold": 0` | `422` | El umbral va de 1 a 100 |
| `GET /points/4/forecasts` | `404` | La Quinta de Juan no es suya: no se revela que existe |
| `GET /points/3/forecasts` | `404` | Potrero Nuevo está en testing |
| `POST /points` con cualquier cuerpo | `403` | Crear puntos es para técnicos |
| `GET /users` | `403` | Listar usuarios es para técnicos |
| `GET /organizations/1/members` | `200` | Ve a los miembros de su organización, pero solo id y nombre |

Sin token, cualquier endpoint salvo el login responde `401`.

## 6. Activar un punto en testing (como técnico)

Entrá como `tecnico@example.com`.

1. `GET /points`: el técnico ve los **cuatro** puntos, incluido Potrero Nuevo en `testing`.
2. `GET /points/3/forecasts`: ve los pronósticos de Potrero Nuevo, todos en `testing`.
3. `PATCH /points/{point_id}` con `point_id` = 3 y el cuerpo `{"status": "active"}`.
4. `GET /points/3/forecasts` otra vez: **los pronósticos siguen en `testing`.** Lo que llegó
   mientras el punto se calibraba es dato de prueba y no se activa.
5. A medida que la ingesta manda lecturas nuevas, esos pronósticos pasan a `active`. En uno
   o dos minutos, la alerta de lluvia de Ana sobre Potrero Nuevo empieza a aparecer en los
   logs del worker, y Ana ya ve el punto en `GET /points`.

## 7. Marcar un pronóstico anómalo

Como técnico:

1. `GET /points/1/forecasts` y elegí el `id` de algún pronóstico.
2. `PATCH /forecasts/{forecast_id}` con `{"status": "disabled"}`. Responde el pronóstico con
   `status: "disabled"`.
3. Ana ya no lo ve en `GET /points/1/forecasts` y no dispara avisos.
4. La marca vale para esa lectura: cuando la ingesta mande la próxima, vuelve a `active`.

Si intentás activar un pronóstico de un punto en testing, la respuesta trae el estado que
quedó guardado: `testing`.

## 8. Administrar usuarios (como admin)

Entrá como `admin@example.com`.

| Endpoint | Qué esperar |
|---|---|
| `GET /users` | Los cuatro usuarios (también lo pueden ver los técnicos) |
| `PATCH /users/4` con `{"role": "technician"}` | Juan pasa a técnico: desde su próximo request ve todos los puntos |
| `PATCH /users/1` con `{"role": "client"}` | `409`: un admin no puede cambiar su propia cuenta, así nunca queda el sistema sin admins |
| `POST /organizations` con `{"name": "Campo Nuevo", "member_ids": [3]}` | Una organización nueva con Ana como miembro |

## 9. Lo mismo con curl

```bash
API=http://localhost:8000

# Login: es un formulario (no JSON), como manda el estándar OAuth2.
TOKEN=$(curl -s -d "username=ana@example.com&password=demo-password" $API/auth/token \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOKEN" $API/points
curl -s -H "Authorization: Bearer $TOKEN" "$API/points/1/forecasts?since=2026-11-12"
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"point_id": 1, "event_type": "rain", "threshold": 40}' $API/alerts
curl -s -H "Authorization: Bearer $TOKEN" "$API/notifications?limit=5"
```

Para entrar con teléfono, el `+` va codificado como `%2B`:

```bash
curl -s -d "username=%2B5493415550402&password=demo-password" $API/auth/token
```

## 10. Mirar la base de datos

```bash
docker compose exec db psql -U weather
```

Algunas consultas útiles:

```sql
-- Avisos por alerta
SELECT a.id, u.name, p.name AS punto, a.event_type, a.threshold, count(n.id) AS avisos
FROM alerts a
JOIN users u ON u.id = a.user_id
JOIN measurement_points p ON p.id = a.point_id
LEFT JOIN notifications n ON n.alert_id = a.id
GROUP BY 1, 2, 3, 4, 5 ORDER BY 1;

-- Re-notificaciones: varios avisos para la misma alerta y el mismo día
SELECT alert_id, forecast_date, string_agg(probability::text, ' → ' ORDER BY id) AS avisos
FROM notifications GROUP BY 1, 2 HAVING count(*) > 1;

-- Estado de los pronósticos de cada punto
SELECT point_id, status, count(*) FROM weather_forecasts GROUP BY 1, 2 ORDER BY 1;
```

## 11. Salud del servicio

```bash
curl -i http://localhost:8000/health      # 200 {"status":"ok"}
docker compose stop db
curl -i http://localhost:8000/health      # 503 Database unavailable
docker compose start db
```

Con la base caída, el worker y la ingesta escriben una línea de error por ciclo y siguen
intentando; cuando la base vuelve, retoman solos.

## 12. Volver a empezar

```bash
docker compose down -v
docker compose up -d --build
```

`-v` borra la base: la demo vuelve a cargar los datos de la sección 2. Sin `-v`, los datos se
conservan y el seed no duplica nada.

## 13. Si algo no anda

| Síntoma | Qué hacer |
|---|---|
| `port is already allocated` | Otro programa usa el puerto. `cp .env.example .env`, cambiá `API_PORT` o `DB_PORT` y volvé a levantar |
| `Cannot connect to the Docker daemon` | Docker no está corriendo: abrí Docker Desktop o `sudo service docker start` |
| La API no responde | `docker compose logs api` y `docker compose logs migrate` |
| No aparecen avisos | `docker compose logs fake_ingest worker`: la ingesta tiene que estar escribiendo y el worker sin errores |
| Login con teléfono falla desde curl | El `+` va como `%2B` (ver la sección 9) |
