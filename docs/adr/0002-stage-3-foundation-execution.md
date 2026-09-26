# ADR 0002: Исполнение этапа 3 поверх bootstrap-контура

Статус: постановка код-стадии AISO-632. База решения: `stage-3-foundation` @ `f938412`. Этот ADR описывает порядок исполнения существующего плана; он не меняет продуктовый объём. Автор постановки не выполняет ревью её реализации.

## Решение и альтернативы

Продолжить девять задач `docs/plans/2026-09-26-stage-3-foundation.md` строго по порядку в уже открытой ветке и PR #4. Bootstrap-файлы сохраняются, Task 1 дополняет существующий CI, а утверждённые дополнения `docs/engineering/bootstrap-contract.md` исполняются в Task 1 и Task 4. Всё, что требует реального VPS, DNS, токенов, ops-группы и внешнего backup-хранилища, остаётся пунктом ожидающей выкладки. Файлы, скрипты, runbook и локальный контейнерный прогон выполняются полностью.

Альтернатива 1 — начать этап 3 с чистого дерева и выполнить буквальное `Create` для CI и bootstrap-файлов. Отвергнута: потеряются уже работающие `boundary`, правила и три коммита PR #4. Альтернатива 2 — выполнить весь план, включая выкладку. Отвергнута: у код-стадии нет реальных доступов; решение владельца — непрерывное производство без выкладки. Критерии выбора: сохранить принятый bootstrap, оставить один PR на этап, обеспечить воспроизводимую локальную проверку и не симулировать живые шаги.

## Границы модулей и контракты

| Владелец | Вход | Выход и контракт |
|---|---|---|
| `config.py` | `POKAZUN_*` | `Settings`, `allowlist`, `webhook_url`, `WEBHOOK_PATH`; prod требует webhook и alert chat, staging — allowlist. |
| `log.py` | События Python/structlog | JSON с context IDs и маской телефонов/токенов, включая вложения и исключения; `alerts.py` применяет ту же маску к тексту. |
| `db/*`, миграция `0001` | PostgreSQL 16 | `Base`, `User`, `ProcessedUpdate`, async sessionmaker; схема меняется только новой миграцией. Тестовая fixture работает только на отдельной БД с guard до `downgrade`/`TRUNCATE`. |
| `bot/*`, `users/repository.py` | Telegram `Update`, `Settings`, транзакция | Access → idempotency → activity → handler внутри одной транзакции; маркер `update_id` коммитится вместе с обработкой. Ошибка откатывает оба изменения и порождает alert. `my_chat_member` не вызывает `touch_user`. |
| `health.py`, `web.py`, `app.py` | DB session, Telegram webhook | `GET /healthz` с таймаутом и 503 при ошибке БД; `POST /tg/webhook` с secret; процесс bot. |
| `worker/*` | `Settings`, DB, backup marker, публичный health URL | Планировщик независимых задач; cleanup маркеров, свежесть backup и HTTPS health с порогом отказов; процесс worker. |
| `deploy/*` | Entrypoints, миграции, `/healthz` | Два Compose-проекта окружений, общий Caddy, локальный/off-VPS backup, deploy и restore runbook. Живая настройка инфраструктуры отложена. |

Граница домена `src/pokazun/search` и `src/pokazun/catalog` от прямого импорта `aiogram` уже защищена `scripts/check_boundaries.py` и CI `boundary`. На этапе 3 каталоги ещё не созданы: зелёный скан означает `0 domain files` вместе с bootstrap self-test/пробами, а не проверку будущего кода. Непрямые импорты остаются `[ревью]`.

## Данные и переходы состояния

Миграция `0001_users.py` создаёт `users` с уникальным `telegram_user_id`, nullable `username`, `first_name`, `phone`, `last_activity_at` и UTC `created_at`/`updated_at`. `subscription_state` принимает `active`, `paused_by_user`, `paused_inactivity`; `telegram_delivery_state` — `active`, `blocked`. Запись `active` для доставки выполняет `touch_user` только на действии пользователя: `message`, `edited_message`, `callback_query`. `my_chat_member` не является таким действием. `processed_updates` содержит PK `update_id` и `processed_at`; вставляет `IdempotencyMiddleware`, а cleanup удаляет записи старше семи дней. Выход для маркера — очистка worker, для неуспешной обработки — rollback; повторная доставка после ошибки обрабатывается заново.

Конкурентная вставка одинакового `update_id` сериализуется уникальным ключом PostgreSQL через `ON CONFLICT DO NOTHING`; маркер и изменения handler принадлежат одной транзакции. Этот контракт требует реального DB-прогона и тестов Task 6. `HealthRegistry` добавляет провайдеры в рамках DB-таймаута. Состояние restart loop пишет `restarts.py` в volume, а worker проверяет marker успешного backup, который пишет `backup.sh` после off-VPS копии.

## Порядок реализации и контрольные точки

Каждая задача: тест из плана → наблюдаемое падение → реализация → проход целевых тестов → `uv run ruff check . && uv run ruff format --check . && uv run pytest` → коммит с дословным сообщением ниже. Шаги внутри задачи не пропускать. Пушить каждый зелёный коммит после этапных тестов; при долгом шаге сохранять WIP-коммит, затем завершить контрольный коммит по плану. Отдельная команда typecheck в плане, bootstrap и текущем CI не определена: не заявлять её пройденной и не вводить новый инструмент молча. Записать команды, exit, `passed/failed/skipped` и замаскированные env в отчёт. Плановые тесты не ослаблять и не пропускать.

1. **Task 1, пакет и CI.** Вход: `.python-version`, `AGENTS.md`, `scripts/check_boundaries.py`, `ci.yml` с `boundary`, `required-checks.md`. Выход: `pyproject.toml`, `uv.lock`, `.gitignore`, `compose.dev.yml`, `src/pokazun/{__init__,clock}.py`, smoke-тесты; расширенный `ci.yml` с `test` и обновлённый реестр required checks. Готово: 2 smoke-теста, ruff, полный pytest, обе CI jobs; красные пробы порога coverage и пустого набора. Коммит: `chore: project skeleton, tooling and CI`.
2. **Task 2, настройки.** Вход: пакет Task 1. Выход: `Settings`, `.env.example`. Готово: 12 тестов `test_config.py`, в том числе prod/staging guard и скрытие секретов. Коммит: `feat: environment-based settings with prod/staging guards`.
3. **Task 3, логи.** Вход: пакет, настройки. Выход: `redact_text`, JSON-конфигурация логов. Готово: 5 тестов `test_log.py`, включая вложения и исключения. Коммит: `feat: JSON logging with phone and credential redaction`.
4. **Task 4, БД.** Вход: `clock.py`, локальный Postgres и отдельный URL. Выход: модели, миграция `0001`, `migrated_db`/`engine`/`sessionmaker`, guard URL. Готово: 4 теста `test_db_migrations.py`, включая `test_models_match_migrations`; отрицательные пробы guard завершаются до разрушения схемы. Коммит: `feat: database models, alembic migrations and test fixtures`.
5. **Task 5, алерты.** Вход: `redact_text`, `utcnow`. Выход: `Alert`, `AlertService`, `format_alert`, `tests.tg` offline Telegram. Готово: 7 тестов `test_alerts.py`, debounce, retry и маска. Коммит: `feat: debounced critical alerts to the ops Telegram group`.
6. **Task 6, dispatcher.** Вход: Settings, БД, алерты и `tests.tg`. Выход: `touch_user`, middleware, `build_dispatcher`, реестр роутеров. Готово: 8 тестов `test_bot_middlewares.py`, включая duplicate, rollback + alert, `my_chat_member`, allowlist. Коммит: `feat: dispatcher with db session, access, idempotency and activity middlewares`.
7. **Task 7, bot/web.** Вход: Settings, DB, alerts, dispatcher. Выход: health registry, webhook, restart detector, bot entrypoint. Готово: 7 тестов `test_health_web.py` + `test_restarts.py`, включая DB-down 503 и secret. Коммит: `feat: web app with healthz and telegram webhook, restart loop detection`.
8. **Task 8, worker.** Вход: DB, alerts, health marker, restart detector. Выход: scheduler, jobs, worker entrypoint. Готово: 8 тестов `test_scheduler.py` + `test_worker_jobs.py`, включая продолжение после ошибки и пороги алертов. Коммит: `feat: worker scheduler with cleanup, backup freshness and public health jobs`.
9. **Task 9, эксплуатационные артефакты.** Вход: оба entrypoint, миграция, health. Выход: Dockerfile, Compose, Caddy, backup/deploy/restore скрипты и runbook. Готово: локальный Step 8 (`config`, миграция, backup, offsite-копия в локальном каталоге, marker); Step 9 и реальные секреты не исполняются, статус «ожидает выкладки». Коммит: `feat: docker compose deployment, https proxy, daily off-site backup and runbook`.

## Принятые дополнения bootstrap

- **Task 1 / R2-S1.** Добавить `pytest-cov` в dev-группу и заменить `addopts` на `-ra --strict-markers --strict-config --cov=src/pokazun --cov-branch --cov-report=term-missing --cov-fail-under=85`. `uv.lock` обновить. `test` выполняет полный `uv run pytest`, без подавления ошибок. Порог 85% общий по линиям и ветвям. Искусственно непокрытая ветка должна дать красный результат; пустой набор — exit 5; после восстановления полный прогон зелёный. Обе замены и причину записать в deviations PR.
- **Task 4 / R3-S1.** До `downgrade(base)`, `TRUNCATE` и прямого `alembic_config(url)` проверять `TEST_DATABASE_URL`: имя строго `pokazun_test_<agent>_<workspace>`, обе части непустые ASCII `[a-z0-9_]+`; исходные host/port/database `POKAZUN_DATABASE_URL` не должны совпадать. `compose.dev.yml` сохраняет стартовую `pokazun_test`, но агент создаёт отдельную БД и подключает только её. В CI service и URL одновременно используют `pokazun_test_ci_<run_id>`. В Task 4 Step 3 меняются подсказка URL и guard, в Step 5 — export URL и предварительное создание БД; ожидаемые 4 passed остаются. Пробы отсутствующего URL, общего имени и совпадения с продуктовой БД красные до очистки; своя БД зелёная. Эти замены также перечислить в deviations PR.

## Приёмка, риски и радиус влияния

До передачи на ревью локально зелёны `uv run ruff check . && uv run ruff format --check . && uv run pytest`; CI `boundary` и `test` зелёны на голове PR #4. Описание PR содержит девять задач, тесты всех пяти пунктов Review Focus и их результат, deviations, чек-лист «Готово, коли» с явным исключением живых пунктов. Заголовок PR меняется на slug код-стадии, который передаст PM. В отчёте указываются дословные команды, числа `passed/failed/skipped`, красно-зелёные пробы и `Step 9: ожидает выкладки`; живое состояние инфраструктуры не заявлять проверенным.

| Ошибка | Радиус | Проверка |
|---|---|---|
| Повторная обработка `update_id` | Дубли действий пользователя | `test_duplicate_update_processed_once` и PK `processed_updates`. |
| Маркер пережил ошибку handler либо нет алерта | Потеря повторной доставки, неразобранный сбой | `test_handler_error_rolls_back_and_alerts`. |
| `my_chat_member` восстановил delivery | Рассылка пользователю, заблокировавшему бота | `test_my_chat_member_is_not_activity`. |
| `/healthz` завис/вернул 500 при недоступной БД | Ложная доступность и поздний alert | `test_healthz_db_down_returns_503`. |
| Телефон/токен попали в лог или alert | Утечка приватных данных | `test_redacts_nested_and_exception`, `test_alert_text_is_redacted`. |
| Конфигурация допускает prod polling или staging без allowlist | Открытый бот либо неверный режим доставки | `test_prod_rejects_polling`, `test_staging_requires_allowlist`. |
| Ошибка одной job остановила worker или не подняла alert | Потеря cleanup и эксплуатационных проверок | `test_failure_alerts_and_loop_continues`, `test_public_health_alerts_after_threshold_and_resets`. |
| Тесты очистили общую/продуктовую БД | Потеря данных соседних работ | Guard Task 4 и красные пробы до миграции. |
| Task 1 перезаписал CI либо не включил coverage | Ложный зелёный PR, утрата проверки границ | `boundary` self-test/пробы, реестр required checks, провокация порога `test`. |
| Backup не дошёл до off-VPS копии или deploy пропустил backup | Невозможность восстановления | Task 9 Step 8 локально и будущий Step 9 на VPS; до выкладки пункт остаётся открытым. |

Неразрешимое расхождение плана с фактом или ошибочный плановый тест — находка для владельца, а не молчаливая правка спецификации. Прямые импорты aiogram держит `[CI: boundary]`; прочие правила `AGENTS.md` пока `[ревью]`, пока не создан соответствующий гейт.
