# aogiritree

AI-powered Conversation Quality Analytics starter for the Freedom Broker 24-hour hackathon.

## Stack
- Python 3.11+
- FastAPI + Uvicorn
- HTML/CSS/Vanilla JS frontend
- JSON-file storage

## Project structure

```text
server/
  __init__.py
  main.py
  evaluator.py
  scoring.py
  checklist.py
  database.py

web/
  index.html
  style.css
  app.js

data/
  checklist.json
  dev_dataset.json
  prod_dataset.json          # создаётся после импорта PROD

results/
  dev/
    results.json
  prod/
    results.json              # создаётся после импорта PROD

requirements.txt
.gitignore
README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run backend

```bash
uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```

Health-check:

```bash
curl http://127.0.0.1:8000/health
```

## Open frontend

Open `http://127.0.0.1:8000/` in a browser after starting the backend.
FastAPI serves the frontend and API from the same origin.

## Initial API endpoints
- `GET /health`
- `GET /api/checklist`
- `PUT /api/checklist`
- `POST /api/datasets/import`
- `GET /api/conversations?group_id=DEV|PROD`
- `GET /api/conversations/{conversation_id}?group_id=DEV|PROD`
- `POST /api/evaluations/{conversation_id}?group_id=DEV|PROD`
- `GET /api/results/{group_id}`
- `GET /api/results/{group_id}/validate`
- `GET /api/appeals`
- `POST /api/appeals`
- `POST /api/evaluations/recalculate`

## Import organizer data

Save the organizer response as JSON and use the `Загрузить GET JSON` button in the UI.
The response must contain `isSuccess: true` and `data.records`. The
`data.dataset_group_id` value selects `DEV` or `PROD` storage.

The local evaluator expects an OpenAI-compatible endpoint, for example LM Studio:

```powershell
$env:LLM_BASE_URL = "http://127.0.0.1:1234/v1"
$env:LLM_MODEL = "qwen/qwen3-4b-2507"
$env:CQA_TEAM_NAME = "Your team"
uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```
