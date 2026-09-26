# Required checks — контракт обязательных проверок `main`

Владелец сверяет этот файл с branch protection ветки `main`. Переименование джобы обновляет этот файл и branch protection в одном PR.

Task 1 этапа 3 расширяет этот файл джобой `test`, не перезаписывая `boundary`.

| Отображаемое имя проверки | CI job ID | Когда обязательна |
|---|---|---|
| `boundary` | `boundary` | с bootstrap, проверяет отсутствие прямых импортов `aiogram` в `src/pokazun/search` и `src/pokazun/catalog` |
| `test` | `test` | с Task 1 этапа 3, `ruff check` + `ruff format --check` + полный `pytest` с PostgreSQL и порогом покрытия 85% |
