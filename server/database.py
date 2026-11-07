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
DEV_DATASET_FILE = DATA_DIR / "dev_dataset.json"
DEV_RESULTS_FILE = RESULTS_DEV_DIR / "results.json"
PROD_DATASET_FILE = DATA_DIR / "prod_dataset.json"
PROD_RESULTS_FILE = RESULTS_PROD_DIR / "results.json"


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
    temporary.replace(path)


def load_checklist() -> dict:
    return read_json(CHECKLIST_FILE, {"criteria": []})


def save_checklist(payload: dict) -> None:
    write_json(CHECKLIST_FILE, payload)


def load_appeals() -> list[dict]:
    return read_json(APPEALS_FILE, [])


def save_appeals(payload: list[dict]) -> None:
    write_json(APPEALS_FILE, payload)


def load_dev_dataset() -> dict:
    return read_json(DEV_DATASET_FILE, {"dataset_group_id": "DEV", "total_records": 0, "records": []})


def save_dev_dataset(payload: dict) -> None:
    write_json(DEV_DATASET_FILE, payload)


def load_prod_dataset() -> dict:
    return read_json(PROD_DATASET_FILE, {"dataset_group_id": "PROD", "total_records": 0, "records": []})


def save_prod_dataset(payload: dict) -> None:
    write_json(PROD_DATASET_FILE, payload)


def load_dev_results() -> dict:
    return read_json(
        DEV_RESULTS_FILE,
        {
            "schema_version": "1.0",
            "team_name": "",
            "model": {"mode": "external_api", "name": ""},
            "results": [],
        },
    )


def save_dev_results(payload: dict) -> None:
    write_json(DEV_RESULTS_FILE, payload)


def load_prod_results() -> dict:
    return read_json(
        PROD_RESULTS_FILE,
        {
            "schema_version": "1.0",
            "team_name": "",
            "model": {"mode": "local", "name": ""},
            "results": [],
        },
    )


def save_prod_results(payload: dict) -> None:
    write_json(PROD_RESULTS_FILE, payload)
