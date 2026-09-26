# Спецификация bootstrap-контура, v2

Статус: постановка для Software Engineer Muse. Решение владельца: bootstrap-файлы идут первыми коммитами ветки `stage-3-foundation`; отдельной ветки `bootstrap` и отдельного PR нет. Приёмка входит в общий PR этапа 3. Исполнитель сначала читает `docs/TEAM-BRIEF.md`, roadmap и целиком план этапа 3 по §1 брифа, затем этот контракт и `docs/adr/0001-bootstrap-contract.md`. Все указанные ниже расхождения с планом явно заносятся в раздел deviations описания PR этапа 3 по §3 и §5 брифа. Редактировать файлы планов для этой постановки нельзя.

## Решение, границы и альтернативы

Цель — дать работающий контракт правил до появления Python-пакета, без создания каркаса раньше Task 1. Выбран автономный `scripts/check_boundaries.py` на stdlib `ast` и CI job `boundary`. Он проверяет прямые `import aiogram` и `from aiogram... import ...` во всех `.py` под `src/pokazun/search` и `src/pokazun/catalog`, включая вложенные блоки, сообщает путь и строку, отвергает синтаксическую ошибку. Строки и комментарии не считаются импортами. Пути вычисляются от корня репозитория, запуск из другого cwd даёт тот же результат.

Альтернатива `ruff` без дополнительного правила не выражает адресный запрет. `import-linter` требует зависимость, `pyproject.toml` и lock до Task 1. Оба варианта отвергнуты по критериям воспроизводимого красного результата, самостоятельности до Task 1 и минимального объёма. AST не видит `importlib`, `__import__` и косвенные зависимости: эти случаи остаются `[ревью]`.

На bootstrap каталогов нет: `0 domain files` допустимо только вместе с успешным `--self-test` и временной пробой каждого реального пути сканирования по процедуре ниже. После появления доменного каталога предикат для него — наличие хотя бы одного `.py`; существующий каталог без `.py` даёт красный результат. Отсутствующий каталог до задачи, которая его создаёт, не ошибка. Реальную пробу на исходнике повторяют в день появления `search/filters.py` (этап 4, Task 1) и `catalog/fields.py`/`record.py` (этап 4, Task 2); это критерий приёмки этих задач, а не обязанность bootstrap создавать продуктовые файлы.

## Артефакты и владельцы

| Артефакт | Первый писатель и контракт |
|---|---|
| `AGENTS.md` | Bootstrap: краткие правила TEAM-BRIEF §4; каждое нормативное предложение имеет `[CI: boundary]` только для прямого aiogram-import либо `[ревью]`. Метка CI меняется в том же PR, где появляется реальная проверка. |
| `.python-version` | Bootstrap: `3.12`; глобальная установка Python не нужна. |
| `scripts/check_boundaries.py` | Bootstrap: основной AST-скан и `--self-test` на разрешённом импорте, обоих запрещённых синтаксисах, строке с текстом импорта и синтаксической ошибке. |
| `.github/workflows/ci.yml` | Bootstrap создаёт `boundary` (ID и отображаемое имя): checkout, Python по `.python-version`, self-test, скан; события `pull_request` и `push` в `main`. Task 1 расширяет файл job `test` и Postgres, не перезаписывает `boundary`. |
| `docs/engineering/required-checks.md` | Bootstrap: отображаемое имя и job ID `boundary`; Task 1 добавляет `test`. Владелец сверяет файл с branch protection `main`; переименование job обновляет оба в одном PR. |
| `docs/engineering/bootstrap-contract.md`, `docs/adr/0001-bootstrap-contract.md` | Настоящая спецификация и ADR; включить в первые коммиты ветки этапа 3. |

Task 1 создаёт `pyproject.toml`, `uv.lock`, `.gitignore`, `compose.dev.yml`, `src/pokazun/__init__.py`, `clock.py` и smoke-тесты. Task 2 создаёт `.env.example`; Task 4 — миграции и БД fixtures. Bootstrap не создаёт `src/`, `tests/`, Compose, зависимости или деплой. Строка `Create: .github/workflows/ci.yml` в Task 1 после bootstrap читается как `Extend`; это отдельное ранее принятое уточнение, также отражаемое в описании PR.

## Контракты исполнения и проверки

`boundary` принимает дерево файлов и возвращает exit 0 только после успешного self-test и отсутствия запрещённого прямого импорта. Красный результат содержит путь/строку или синтаксическую ошибку. При отсутствии обоих доменных каталогов основной скан явно печатает `0 domain files`; self-test и временные пробы обязательны. При появлении каталога без `.py` красный результат защищает от ложного зелёного скана.

### Временная проба границы на bootstrap (R1-S1)

1. Убедиться, что `src/pokazun/search` и `src/pokazun/catalog` отсутствуют. Записать начальный `git status --porcelain --untracked-files=all` и зелёный exit `python scripts/check_boundaries.py --self-test` и `python scripts/check_boundaries.py`.
2. Для `search` создать только временный каталог и `src/pokazun/search/__boundary_probe__.py` с `import aiogram`. Записать `git status --porcelain --untracked-files=all`: строка `?? src/pokazun/search/__boundary_probe__.py` обязательна; `git diff` для untracked файла не служит доказательством. Запустить `python scripts/check_boundaries.py`, сохранить ненулевой exit и сообщение о файле и строке. Удалить только созданный файл и пустой каталог; повторить скан до exit 0 и проверить статус против начального.
3. Повторить пункт 2 отдельно для `catalog`, с `src/pokazun/catalog/__boundary_probe__.py` и `from aiogram import Bot`. Записать красный exit, затем удаление и зелёный повтор. Не удалять чужие файлы и не применять `git checkout --` к чужой работе. Если каталог уже существует, использовать резервную копию своего реального `.py`, фиксировать непустой `git diff`, восстановить ровно свой файл.
4. В отчёте для обеих проб указать точные команды, exit, фрагмент вывода, строки `git status --porcelain` до/во время/после. Отдельно подтвердить разрешённый импорт и синтаксическую ошибку через self-test. На этапе 4 повторить нарушение уже на реально созданном `.py` соответствующей задачи с непустым diff, красным exit, точным восстановлением и зелёным повтором.

Команды для пробы `search` при исходно отсутствующем каталоге (код выхода сканера фиксировать сразу после его вызова):

```sh
mkdir -p src/pokazun/search
printf 'import aiogram\n' > src/pokazun/search/__boundary_probe__.py
git status --porcelain --untracked-files=all
python scripts/check_boundaries.py
printf 'boundary exit=%s\n' "$?"
rm src/pokazun/search/__boundary_probe__.py
rmdir src/pokazun/search
python scripts/check_boundaries.py
git status --porcelain --untracked-files=all
```

Для `catalog` заменить в этих командах `search` на `catalog` и строку `import aiogram` на `from aiogram import Bot`; ожидаемый первый exit ненулевой, после удаления — ноль. Файлы и каталоги удалять только после проверки, что их создала эта проба; при наличии каталога действовать по пункту 3, а не выполнять `rmdir`.

### Дополнения к плану этапа 3 (deviation): Task 1, R2-S1

План Task 1 Step 1 задаёт dev-группу `pytest`, `pytest-asyncio`, `ruff` и `addopts = "-ra --strict-markers"`. В том же `pyproject.toml` **добавить** `pytest-cov` в dev-группу и **заменить** значение addopts на `"-ra --strict-markers --strict-config --cov=src/pokazun --cov-branch --cov-report=term-missing --cov-fail-under=85"`; обновить `uv.lock`. Порог 85% — совокупное покрытие линий и ветвей, не каждого модуля. Task 1 Step 8 job `test` выполняет полный `uv run pytest` с этими опциями, без подавления ошибки или исключения тестов; пустой набор даёт exit 5. `-ra` показывает skipped/xfail; в отчёте исполнителя записать `passed/failed/skipped`, включая `skipped=0`. Плановые тесты нельзя skip/xfail; новые пропуски требуют причины и решения владельца. Живая проба: искусственно непокрытая ветка должна опустить покрытие ниже 85 и покраснить `test`; пустая выборка должна дать exit 5; после восстановления полный прогон зелёный. Точные команды, код выхода и числа прогонов записать в PR. Это изменение объёма Task 1 **deviation**, в описании PR этапа 3 перечислить обе замены и причину — контракт bootstrap-чеклиста.

### Дополнение к плану этапа 3 (deviation): Task 4, R3-S1

До первой разрушающей операции (`downgrade(base)`, `TRUNCATE`, будущий `DROP SCHEMA`) `tests/conftest.py` разбирает `TEST_DATABASE_URL` через SQLAlchemy и допускает только имя БД `pokazun_test_<agent>_<workspace>` с непустыми slug из ASCII `[a-z0-9_]+`. Запускающий агент задаёт свои `agent` и `workspace`, создаёт ровно эту БД и удаляет её после работы; fixture владеет только схемой/очисткой. Guard отвергает пустой URL, неподходящее имя и БД, совпадающую с исходным `POKAZUN_DATABASE_URL` по host/port/database (до того как `alembic_config` временно выставит этот env в тестовый URL). Guard должен действовать и при прямом вызове `alembic_config(url)` из теста. Ошибка останавливает тест до миграции и очистки.

Точные чтения примеров плана после этого deviation:

| Место плана | Что исполнитель делает |
|---|---|
| Task 1 Step 3, `compose.dev.yml`, `POSTGRES_DB: pokazun_test` | Строка остаётся: это стартовая БД локального сервера Postgres, **не** допустимый URL для разрушающих тестов. До тестов агент создаёт в контейнере свою `pokazun_test_<agent>_<workspace>`. |
| Task 1 Step 8, CI service `POSTGRES_DB: pokazun_test` и `TEST_DATABASE_URL: .../pokazun_test` | Обе строки **заменяются согласованно** на `pokazun_test_ci_<run_id>` (например, `${{ github.run_id }}`), где `agent=ci`, `workspace=<run_id>`; service создаёт эту БД, env указывает на неё. Изолированный CI job не использует локальную общую БД. |
| Task 4 Step 3, `_test_database_url()` | Сохранить громкий fail при отсутствующем `TEST_DATABASE_URL`; заменить подсказку с `/pokazun_test` на шаблон и добавить guard имени и сравнение с исходным `POKAZUN_DATABASE_URL` до `alembic_config`/`downgrade`. Проверить также прямой путь через `alembic_config(url)`. |
| Task 4 Step 5, `export TEST_DATABASE_URL=.../pokazun_test` | **Заменить** URL на `.../pokazun_test_<agent>_<workspace>`, предварить команду созданием именно этой БД после `docker compose -f compose.dev.yml up -d`. Ожидаемые 4 passed из плана остаются критерием. |

Для CI `ci` и `run_id` дают требуемые две части имени. Не полагаться на пример Compose или общий `pokazun_test` как на разрешение к разрушительному тесту. Красные пробы: URL отсутствует, имя `pokazun_test`, URL совпадает с исходным `POKAZUN_DATABASE_URL`; все завершаются до очистки. Зелёная проба: своя БД. Команды, exit и masked URL в отчёте. Это deviation объёма Task 4 и затрагивающего его CI-примера Task 1; обе точные замены записать в описании PR этапа 3.

## Матрица bootstrap-чеклиста

| Пункт | Артефакт или N/A |
|---|---|
| Правила машины | `AGENTS.md` с метками. Перенести TEAM-BRIEF §4: TDD и неприкосновенность тестов, отсутствие заглушек, границы этапов, секреты, Airtable GET/allowlist, приватные поля, маску телефонов, отдельные staging/prod, миграции и `test_models_match_migrations`, UTC/`now`, тексты в `texts.py`, deploy/backup. Явно включить fail БД-тестов без `TEST_DATABASE_URL` и запрет ручных изменений на prod. Пока нет конкретной CI-проверки — `[ревью]`. |
| Граница | AST-гейт и `boundary`; временная проба каждого пути на bootstrap, повторная проба реального файла при создании каталогов на этапе 4. |
| Раннер | Task 1 `pyproject.toml`, `uv.lock`, `test`, дополнение R2-S1; пустой прогон красный, skipped видны. Task 4 guard R3-S1. |
| Required checks | `docs/engineering/required-checks.md` и branch protection: сначала `boundary`, после Task 1 также `test`. |
| Один писатель | `[ревью]` в `AGENTS.md`: один писатель на task worktree; управляемый checkout через Multica. Ручной `git worktree` внутри task workdir N/A. |
| Scorecard | PM ведёт с первого круга в репозитории `scorecard`; для bootstrap-файлов N/A. |
| Исключения сканеров | Gitleaks/CodeQL не вводятся, поэтому реестр в bootstrap N/A. При введении создать реестр с причиной, владельцем и сроком каждой записи; погашенные выводить в каждом прогоне. |
| БД каждого агента | Task 4 guard и конвенция выше; общий Postgres из Task 1 не равен общей тестовой БД. |
| Outbox | Код N/A до этапа событий. До его реализации определить писателя, worker, идемпотентность, retry, терминальный выход и двойной аудит. |
| Локальный контур | Task 1 `docker compose -f compose.dev.yml up -d` даёт PostgreSQL 16; кэш/S3 N/A по текущей архитектуре. |
| Рантайм | `.python-version` 3.12; Task 1 `uv.lock`, `uv sync --frozen`; npm/pnpm/commitlint N/A. |

## Порядок исполнения и готовность

1. В первых коммитах `stage-3-foundation` перенести документы, `.python-version`, `AGENTS.md` и `required-checks.md`; у всех правил сверить метки. Следующим коммитом добавить AST-гейт и CI `boundary`. Снять доказательства временных проб и self-test до продуктового кода.
2. Task 1 исполнить по плану с указанными deviation: создать пакет и зависимости, расширить CI job `test`, обновить required checks, получить зелёные ruff/pytest и красно-зелёные пробы порога/пустого прогона.
3. Task 4 исполнить по плану с guard; проверить обе ветки допуска БД до миграции. Дальше выполнять план этапа 3 по порядку. Этап 4 Task 1 и Task 2 повторяют пробу границы на живых файлах в день их создания.
4. В описании общего PR этапа 3 перечислить все deviations, соответствие CI имён required-checks и доказательства: дословная команда, exit, существенный красный/зелёный вывод, `passed/failed/skipped`, masked URL. Владелец принимает общий PR; отдельного bootstrap-PR нет.

Ошибочный гейт оставляет домен связанным с aiogram; радиус — код этапов 4–5. Неполное покрытие или неверное имя required check оставляет ложный зелёный `main`. Общая тестовая БД может быть очищена миграциями другого агента; радиус — все параллельные локальные прогоны. Изменение CI без сохранения `boundary` снимает защиту всех будущих доменных файлов. Эти риски удерживаются указанными пробами, именами job и guard до разрушающих операций.
