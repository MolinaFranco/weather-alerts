# Qué está testeado

99 tests (157 casos contando los parametrizados), todos contra un Postgres real.

## Cómo se corren

```bash
docker compose up -d db
uv run pytest
```

Si cambiaste el puerto de la base (`DB_PORT`), indicá la base de test:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://weather:weather@localhost:5433/weather_test uv run pytest
```

## Cómo están armados

Corren contra un Postgres real y no contra SQLite, porque el sistema depende de enums,
triggers, `ON CONFLICT`, `SKIP LOCKED` y advisory locks. La base de test se migra una vez al
arrancar, con las mismas migraciones que producción.

Todo lo que hace un test, incluidos los `commit()` de la API, corre dentro de una
transacción que se deshace al terminar, así los tests no se pisan y no hace falta limpiar a
mano. Cada request de la API tiene su propia sesión, como en producción, sobre esa misma
transacción. Los pocos tests que necesitan varias conexiones a la vez (concurrencia)
commitean de verdad y vacían las tablas al final.

Los datos se arman con funciones chicas de `tests/factories.py`, y cada test crea solo lo
que usa.

Para las reglas más delicadas se comprobó que su test falla si se quita la regla: el filtro
por estado del punto en el evaluador, el advisory lock, `SKIP LOCKED`, el lock solo sobre la
fila del aviso, la regla de visibilidad en el evaluador y en el dispatcher, el rearmado al
subir el umbral y que lo recibido durante el testing no se active.

## Base de datos y migraciones

| Qué se prueba | Test |
|---|---|
| Las migraciones bajan hasta el principio y vuelven a subir sin errores | `test_migrations.py::test_migrations_go_down_and_up_cleanly` |
| Los modelos coinciden con las migraciones (`alembic check`) | `test_migrations.py::test_models_match_migrations` |
| Un punto tiene exactamente un dueño: ni ninguno ni dos | `test_models.py::test_point_must_have_exactly_one_owner` |
| No se repite el nombre de un punto para un mismo dueño | `test_models.py::test_point_names_are_unique_per_owner` |
| Dueños distintos sí pueden repetir nombres | `test_models.py::test_point_names_can_repeat_across_owners` |
| El email es único sin importar mayúsculas | `test_models.py::test_user_email_is_unique_ignoring_case` |
| El teléfono es único y está en formato E.164 | `test_models.py::test_user_phone_is_unique_and_in_e164_format` |
| Un usuario no se suma dos veces a la misma organización | `test_models.py::test_a_user_joins_an_organization_once` |
| La probabilidad de un pronóstico va de 0 a 100 | `test_models.py::test_forecast_probability_is_a_percentage` |
| Un pronóstico por punto, día y evento | `test_models.py::test_one_forecast_per_point_day_and_event` |
| El umbral de una alerta va de 1 a 100 | `test_models.py::test_alert_threshold_is_between_1_and_100` |
| Una alerta por usuario, punto y evento | `test_models.py::test_one_alert_per_user_point_and_event` |
| El mismo aviso nunca se guarda dos veces | `test_models.py::test_the_same_notification_is_never_stored_twice` |
| Borrar un punto borra sus pronósticos y alertas | `test_models.py::test_deleting_a_point_removes_its_forecasts_and_alerts` |

## Estado de puntos y pronósticos (triggers)

Probado con upserts, que es como escribe la ingesta.

| Qué se prueba | Test |
|---|---|
| Un pronóstico que llega a un punto en testing o dado de baja toma ese estado | `test_sample_status.py::test_samples_take_the_status_of_a_point_that_is_not_active` |
| Datos nuevos de un punto dado de baja quedan dados de baja | `test_sample_status.py::test_new_data_on_a_point_that_was_disabled_is_disabled` |
| Una marca manual dura hasta la próxima lectura | `test_sample_status.py::test_a_manual_mark_lasts_until_the_next_reading` |
| No se puede activar un pronóstico mientras su punto está en testing | `test_sample_status.py::test_a_sample_cannot_be_activated_while_its_point_is_testing` |
| Lo recibido durante el testing sigue siendo de prueba al activar el punto; la próxima lectura sí cuenta | `test_sample_status.py::test_readings_from_the_testing_period_stay_test_data` |
| Una lectura que repite el valor igual cuenta como lectura nueva | `test_sample_status.py::test_a_reading_that_repeats_the_value_is_still_a_new_reading` |
| Cada actualización renueva `updated_at`, aunque escriba un sistema externo | `test_sample_status.py::test_updates_refresh_updated_at` |

## Evaluación de alertas

La evaluación está escrita de dos formas equivalentes: con SQL (`app/jobs/evaluator.py`, la
que usa el worker) y con el query builder de SQLAlchemy (`app/jobs/evaluator_query_builder.py`, como
alternativa para comparar). Cada test de esta sección corre contra las dos.

| Qué se prueba | Test |
|---|---|
| Avisa cuando la probabilidad alcanza el umbral (60 con umbral 60 sí, 59 no) | `test_evaluator.py::test_notifies_when_the_probability_reaches_the_threshold` |
| Ignora otros eventos | `test_evaluator.py::test_ignores_other_events` |
| Ignora días pasados | `test_evaluator.py::test_ignores_past_days` |
| Ignora alertas pausadas | `test_evaluator.py::test_ignores_inactive_alerts` |
| Ignora pronósticos o puntos que no están activos | `test_evaluator.py::test_ignores_data_that_is_not_active` |
| Un punto que pasa a testing deja de avisar por sus pronósticos ya guardados | `test_evaluator.py::test_a_point_put_in_testing_stops_notifying_its_existing_forecasts` |
| Correr la evaluación dos veces no duplica avisos | `test_evaluator.py::test_running_twice_does_not_notify_twice` |
| Re-avisa solo si la probabilidad sube 15 puntos o más (65 → 79 → 50 → 80 → 90 avisa en 65 y 80) | `test_evaluator.py::test_notifies_again_only_when_the_probability_rises_enough` |
| Un aviso que falló no cuenta como enviado | `test_evaluator.py::test_a_notice_that_never_reached_the_user_does_not_count` |
| Cada día se avisa por separado | `test_evaluator.py::test_each_day_is_notified_on_its_own` |
| Subir el umbral vuelve a habilitar la alerta | `test_evaluator.py::test_raising_the_threshold_rearms_the_alert` |
| Pausar y reactivar una alerta no repite un aviso | `test_evaluator.py::test_a_reactivated_alert_does_not_repeat_a_notice` |
| Todos los miembros que vigilan un punto compartido reciben su aviso | `test_evaluator.py::test_every_member_watching_a_shared_point_is_notified` |
| Alguien sacado de la organización deja de recibir avisos de sus puntos | `test_evaluator.py::test_someone_removed_from_the_organization_stops_being_notified` |
| El staff recibe avisos de cualquier punto | `test_evaluator.py::test_staff_hear_about_any_point` |
| Dos evaluaciones a la vez se turnan y no avisan dos veces una misma subida | `test_evaluator.py::test_evaluations_take_turns` |

## Envío de avisos

| Qué se prueba | Test |
|---|---|
| Envía el próximo aviso, lo marca enviado y avisa cuando no queda nada | `test_dispatcher.py::test_sends_the_next_due_notice_and_marks_it_sent` |
| Envía primero el más viejo | `test_dispatcher.py::test_sends_the_oldest_notice_first` |
| Solo envía avisos pendientes | `test_dispatcher.py::test_only_pending_notices_are_sent` |
| Descarta avisos de alertas pausadas, puntos en testing y días pasados | `test_dispatcher.py::test_skips_notices_that_no_longer_apply` |
| Descarta avisos de alguien que dejó la organización | `test_dispatcher.py::test_a_notice_for_someone_who_left_the_organization_is_skipped` |
| Un envío fallido se reintenta a 1, 2, 4 y 8 minutos y al quinto queda fallido | `test_dispatcher.py::test_a_failed_send_is_retried_with_growing_waits` |
| Un envío que se cuelga corta por timeout y cuenta como fallo | `test_dispatcher.py::test_a_send_that_hangs_counts_as_failed` |
| Dos workers se reparten la cola sin esperarse ni repetir avisos | `test_dispatcher.py::test_concurrent_dispatchers_split_the_queue` |
| El texto del aviso, tal como lo leería el usuario | `test_notifier.py::test_the_message_reads_like_a_whatsapp_text` |
| Todos los eventos tienen nombre en castellano | `test_notifier.py::test_every_event_has_a_name` |

## Worker

| Qué se prueba | Test |
|---|---|
| Un ciclo completo: pronóstico → aviso enviado | `test_worker.py::test_a_cycle_evaluates_and_sends` |
| Al apagarse, encola pero no empieza envíos nuevos | `test_worker.py::test_a_stopping_worker_queues_notices_but_does_not_send_them` |
| Un ciclo que falla no detiene el worker | `test_worker.py::test_the_loop_survives_a_failed_cycle` |
| La señal de apagado corta la espera sin esperar el intervalo | `test_worker.py::test_the_loop_stops_without_waiting_out_the_interval` |
| Una zona horaria inexistente impide arrancar | `test_config.py::test_an_unknown_timezone_stops_the_app_from_starting` |

## Autenticación y permisos

| Qué se prueba | Test |
|---|---|
| Cada endpoint de staff devuelve 403 al rol justo debajo del mínimo (14 casos) | `test_permissions.py::test_a_role_below_the_minimum_is_forbidden` |
| Todos los endpoints salvo login piden token (24 casos) | `test_permissions.py::test_every_route_but_login_needs_a_token` |
| El registro crea un cliente y no devuelve la contraseña | `test_auth.py::test_register_creates_a_client` |
| Registrarse mandando un rol igual da un cliente | `test_auth.py::test_signing_up_never_grants_a_role` |
| Un email o teléfono no se registra dos veces | `test_auth.py::test_an_email_or_phone_can_only_register_once` |
| Rechaza email, teléfono, contraseña o nombre inválidos | `test_auth.py::test_register_rejects_invalid_data` |
| Login con email (en cualquier mayúscula) o con teléfono | `test_auth.py::test_login_works_with_email_or_phone` |
| Login falla con contraseña incorrecta o usuario inexistente | `test_auth.py::test_login_fails_with_wrong_credentials` |
| Rechaza tokens vencidos, falsificados, de usuarios borrados o sin vencimiento | `test_auth.py::test_expired_forged_orphan_or_endless_tokens_are_rejected` |
| `/me` muestra las organizaciones del usuario | `test_auth.py::test_me_shows_my_organizations` |

## API por recurso

| Qué se prueba | Test |
|---|---|
| Staff crea un cliente ya dentro de organizaciones | `test_users.py::test_staff_create_a_client_inside_organizations` |
| Crear un usuario en una organización inexistente no deja nada a medias | `test_users.py::test_creating_a_user_in_a_missing_organization_creates_nothing` |
| Técnicos listan usuarios | `test_users.py::test_technicians_list_users` |
| Admins cambian roles y borran usuarios | `test_users.py::test_admins_change_roles_and_delete_users` |
| Un admin no puede cambiar ni borrar su propia cuenta | `test_users.py::test_admins_cant_change_or_delete_their_own_account` |
| Borrar un usuario borra sus puntos particulares | `test_users.py::test_deleting_a_user_removes_their_own_points` |
| Cambiar un usuario inexistente da 404 | `test_users.py::test_changing_a_missing_user_is_a_404` |
| Staff crea una organización con miembros | `test_organizations.py::test_staff_create_an_organization_with_members` |
| Una organización puede arrancar sin miembros | `test_organizations.py::test_an_organization_can_start_without_members` |
| Una organización con un miembro inexistente no se crea | `test_organizations.py::test_an_organization_with_a_missing_member_is_not_created` |
| Clientes ven sus organizaciones; staff ve todas; las ajenas dan 404 | `test_organizations.py::test_clients_only_see_their_organizations_and_staff_see_all` |
| Los miembros solo ven el nombre de los demás, no su contacto | `test_organizations.py::test_members_only_see_each_others_names` |
| Agregar (204), repetir (409), sacar (204) y volver a sacar (404) un miembro | `test_organizations.py::test_members_are_added_once_and_can_be_removed` |
| Agregar a una organización o un usuario inexistente falla | `test_organizations.py::test_adding_to_a_missing_organization_or_a_missing_user_fails` |
| Técnicos renombran, admins borran | `test_organizations.py::test_staff_rename_and_admins_delete` |
| Un cliente ve sus puntos y los activos de sus organizaciones, nada más | `test_points.py::test_clients_see_their_own_and_their_organizations_active_points` |
| El staff ve todos los puntos en cualquier estado | `test_points.py::test_staff_see_every_point_in_any_status` |
| Un cliente no ve su propio punto mientras está en testing | `test_points.py::test_a_client_cant_see_their_own_point_while_it_is_in_testing` |
| Staff crea y modifica puntos | `test_points.py::test_staff_create_and_update_points` |
| Un punto necesita exactamente un dueño (validación de la API) | `test_points.py::test_a_point_needs_exactly_one_owner` |
| Dueño inexistente da 422; nombre repetido da 409 | `test_points.py::test_a_point_for_a_missing_owner_or_with_a_taken_name_is_refused` |
| Al modificar un punto devuelve las coordenadas guardadas | `test_points.py::test_an_updated_point_returns_the_coordinates_as_stored` |
| Clientes reciben solo pronósticos activos; staff, todos | `test_points.py::test_clients_only_get_active_forecasts_and_staff_get_all` |
| Los pronósticos se filtran por fecha | `test_points.py::test_forecasts_can_be_filtered_by_date` |
| Un rango de fechas al revés da 422 | `test_points.py::test_a_date_range_that_ends_before_it_starts_is_rejected` |
| Pronósticos de un punto ajeno dan 404 | `test_points.py::test_forecasts_of_a_point_you_cant_see_are_a_404` |
| Marcar un pronóstico devuelve el estado que quedó en la base | `test_points.py::test_marking_a_forecast_returns_the_status_the_database_kept` |
| Admins borran puntos y pronósticos | `test_points.py::test_admins_delete_points_and_forecasts` |
| Un cliente crea una alerta sobre un punto que ve | `test_alerts.py::test_a_client_creates_an_alert_on_a_point_they_see` |
| Alertas sobre puntos ajenos o en testing dan 404 | `test_alerts.py::test_alerts_on_points_you_cant_see_are_a_404` |
| Una alerta por punto y evento, umbral de 1 a 100 | `test_alerts.py::test_one_alert_per_point_and_event_with_a_threshold_from_1_to_100` |
| Cada usuario ve y modifica solo sus alertas | `test_alerts.py::test_users_only_see_and_change_their_own_alerts` |
| Ids fuera del rango de la base dan 422, no un error 500 | `test_alerts.py::test_ids_beyond_the_database_range_are_rejected_not_a_crash` |
| Avisos propios, más nuevos primero, paginados | `test_notifications.py::test_notifications_are_mine_newest_first_and_paged` |
| La paginación tiene límites | `test_notifications.py::test_page_sizes_are_bounded` |
| `/health` responde 200 | `test_health.py::test_health_ok` |
| `/health` responde 503 si la base no responde | `test_health.py::test_health_returns_503_when_the_database_is_unreachable` |

## Qué no está testeado

- `LogNotifier`, que solo escribe en el log.
- Los mocks de la demo (`app/mocks/`): reemplazan sistemas externos y se probaron
  levantando la demo completa.
- El comando `create_admin`, más allá de usar el mismo schema que el registro.
