# Zeabur Deployment

## First-Time Setup
1. Push this repository to GitHub.
2. In Zeabur, create a new project and choose `Deploy from GitHub repo`.
3. Select this repository and let Zeabur detect the Python service.
4. Zeabur will use [`zbpack.json`](/home/ajin/insurance-product-recommand-demo/zbpack.json) to pin the Python entrypoint and package manager.
5. Add the required environment variables before the first successful deploy.

## Build and Start
- Install step: Zeabur auto-installs dependencies from `requirements.txt`
- Entrypoint: `app.py`
- Health check endpoint: `/health`
- If you must override the start command in the Zeabur UI, use:
  `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Required Variables
- `INSURANCE_LLM_API_KEY`: your LLM provider API key
- `INSURANCE_LLM_MODEL`: model name, for example `gpt-4o`
- `INSURANCE_LLM_BASE_URL`: optional, only for OpenAI-compatible gateways

## Auto Deploy
After the repository is linked, every push to the tracked GitHub branch triggers a new Zeabur deployment automatically.

## Notes
- The site serves the existing single-page UI at `/`.
- Product data is loaded from `data/*.xlsx` during startup.
- Do not commit private keys; keep them in Zeabur Variables only.
- Zeabur supports FastAPI and recognizes `app.py` as a Python entrypoint.
- The existing `render.yaml` can be ignored if Zeabur is your chosen platform.
