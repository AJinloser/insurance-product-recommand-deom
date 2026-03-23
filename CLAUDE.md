# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Insurance product recommendation engine (Chinese medical insurance). Takes user queries, dialogue history, and profiles as input, then recommends suitable products from a SQLite database populated from Excel files. Uses LLM (via LangChain/OpenAI-compatible API) for query construction and product scoring.

## Setup & Running

```bash
pip install -r requirements.txt
# Configure .env from .env.example (set INSURANCE_LLM_API_KEY, INSURANCE_LLM_BASE_URL, INSURANCE_LLM_MODEL)
python example_usage.py   # runs all 8 test cases
```

No test framework is configured. `example_usage.py` serves as the integration test suite.

## Architecture

**4-step recommendation pipeline** (`src/engine/agent.py` → `InsuranceRecommendationAgent.recommend()`):

1. **QueryConstructor** (`engine/steps/query_constructor.py`) — LLM extracts hard constraints (SQL) and soft preferences (text list) from user input
2. **HardFilter** (`engine/steps/hard_filter.py`) — Executes LLM-generated SQL against SQLite; falls back to all products on error
3. **SoftScorer** (`engine/steps/soft_scorer.py`) — LLM scores filtered candidates on 6 dimensions, returns ranked JSON
4. **OutputAssembler** (`engine/steps/output_assembler.py`) — Packs scored results into `RecommendationOutput`

**Data layer:**
- Excel files in `data/` (transposed format: rows=fields, columns=products) → parsed by `data_loader/excel_parser.py`
- `data_loader/field_classifier.py` auto-classifies fields as hard (numeric/boolean, SQL-filterable) or soft (text, LLM-evaluated)
- EAV schema in SQLite (`insurance.db`): `products`, `product_values`, `field_metadata` tables
- `data_loader/loader.py` orchestrates idempotent load from Excel → SQLite

**Key design decisions:**
- EAV (Entity-Attribute-Value) database model allows arbitrary insurance product fields without schema changes
- LLM generates SQL with JOINs on `product_values` for each hard constraint
- Dangerous SQL keywords are blocked before execution (`QueryConstructor._parse`)
- All config via `INSURANCE_*` env vars, loaded through `Settings.from_env()`

## Data Contracts

- Input: `RecommendationInput` (query + dialogue_history + UserProfile)
- Output: `RecommendationOutput` (status + list of `ProductRecommendation` with reasoning)
- Defined in `src/models/schemas.py`

## LLM Prompts

All prompt templates live in `src/engine/prompts.py`. Two prompts:
- `QUERY_CONSTRUCTOR_*` — extracts constraints, generates SQL
- `SOFT_SCORER_*` — scores candidates across 6 dimensions, outputs structured JSON

## Language

Product data, prompts, and user-facing text are in Chinese. Code, comments, and docstrings are in English.
