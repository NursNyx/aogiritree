from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DEV_DIR = BASE_DIR / "results" / "dev"
RESULTS_PROD_DIR = BASE_DIR / "results" / "prod"
CHECKLIST_FILE = DATA_DIR / "checklist.json"
APPEALS_FILE = RESULTS_DEV_DIR / "appeals.json"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DEV_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PROD_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_checklist() -> dict:
    return read_json(CHECKLIST_FILE, {"criteria": []})


def save_checklist(payload: dict) -> None:
    write_json(CHECKLIST_FILE, payload)


def load_appeals() -> list[dict]:
    return read_json(APPEALS_FILE, [])


def save_appeals(payload: list[dict]) -> None:
    write_json(APPEALS_FILE, payload)
