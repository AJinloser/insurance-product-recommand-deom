# Render Deployment

## First-Time Setup
1. Push this repository to GitHub.
2. In Render, create a new Web Service from the GitHub repo.
3. Render will detect `render.yaml` automatically.
4. Set `INSURANCE_LLM_API_KEY` in the Render dashboard before the first successful deploy.
5. If you use a compatible proxy or gateway, also set `INSURANCE_LLM_BASE_URL`.

## Runtime
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

## Auto Deploy
Once the service is connected, every push to the tracked GitHub branch triggers a new deployment automatically.

## Notes
- The service serves the existing single-page UI at `/`.
- Product data is loaded from `data/*.xlsx` during startup.
- The free Render plan may cold-start after inactivity, so the first request can be slow.
