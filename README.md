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

results/
  dev/
    .gitkeep
  prod/
    .gitkeep

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

Open `/home/runner/work/aogiritree/aogiritree/web/index.html` in a browser
(or serve the `web/` folder with any static file server).

The frontend expects backend API at `http://127.0.0.1:8000`.

## Initial API endpoints
- `GET /health`
- `GET /api/checklist`
- `PUT /api/checklist`
- `GET /api/conversations/demo` (demonstration-only conversation scaffold)
- `GET /api/appeals`
- `POST /api/appeals`
- `POST /api/evaluations/recalculate` (review/appeal-ready score recalculation scaffold)
