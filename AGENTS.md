# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `src/`. Use `src/engine/` for the recommendation pipeline, `src/data_loader/` for Excel-to-SQLite ingestion, `src/database/` for persistence, and `src/models/` for Pydantic contracts. Runtime entrypoints are `app.py` for the FastAPI demo, `example_usage.py` for scripted scenarios, and `test_runner.py` for the HTML test report flow. Source data is stored in `data/*.xlsx`, methodology notes in `docs/`, and the generated SQLite database at `insurance.db`.

## Build, Test, and Development Commands
Install dependencies with `pip install -r requirements.txt`.
Run the scenario suite with `python example_usage.py`.
Run the visual test harness with `python test_runner.py --all` or inspect cases with `python test_runner.py --list`.
Start the web demo with `uvicorn app:app --reload` if FastAPI and Uvicorn are available in your environment.
When data files change, call `agent.load_data(force_reload=True)` or rerun the scripts that bootstrap the database.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, type hints, small focused classes, and `snake_case` for modules, functions, and variables. Keep Pydantic models and public contracts explicit in `src/models/schemas.py`. Prefer English for code, comments, and docstrings; keep user-facing product text and prompts in Chinese to match the dataset. Use concise docstrings on non-trivial classes and methods. No formatter or linter is configured here, so match the surrounding style carefully.

## Testing Guidelines
This repository uses executable scenario tests rather than `pytest`. Add new coverage by extending the `TEST_CASES` lists in `example_usage.py` or `test_runner.py`. Name cases by business scenario, not by implementation detail, for example `“高端全球医疗 — 高预算”`. Before submitting changes, run the affected scenario set and confirm recommendations still return `status="success"`.

## Commit & Pull Request Guidelines
Git history is not available in this workspace snapshot, so no repository-specific commit pattern can be inferred. Use short imperative commit messages such as `Add newborn filtering scenario` or `Tighten hard-filter SQL parsing`. PRs should summarize behavior changes, note any data or prompt updates, include screenshots for `frontend.html` or report changes, and list the commands used for validation.

## Configuration Tips
Configuration is loaded from `INSURANCE_*` environment variables in `src/config.py`. At minimum, set `INSURANCE_LLM_API_KEY`; optionally set `INSURANCE_LLM_BASE_URL`, `INSURANCE_LLM_MODEL`, and custom paths for data or the database before running local tests.
