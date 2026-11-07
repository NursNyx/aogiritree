from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .checklist import ChecklistConfig
from .database import (
    ensure_directories, load_appeals, load_checklist, load_dev_dataset,
    load_dev_results, load_prod_dataset, load_prod_results, save_appeals,
    save_checklist, save_dev_dataset, save_dev_results, save_prod_dataset,
    save_prod_results,
)
from .evaluator import (
    Appeal, Conversation, DEMO_CONVERSATION, ErrorResult, EvaluationResult,
    OpenAICompatibleEvaluator, ReviewerDecision, recalculate_result,
)

app = FastAPI(title="Freedom Broker CQA", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1:8000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrganizerResponse(BaseModel):
    error: str = ""
    isSuccess: bool
    data: dict[str, Any]


def _dataset(group_id: str) -> dict:
    normalized = group_id.upper()
    if normalized == "DEV":
        return load_dev_dataset()
    if normalized == "PROD":
        return load_prod_dataset()
    raise HTTPException(status_code=400, detail="group_id must be DEV or PROD")


def _results(group_id: str) -> dict:
    normalized = group_id.upper()
    if normalized == "DEV":
        return load_dev_results()
    if normalized == "PROD":
        return load_prod_results()
    raise HTTPException(status_code=400, detail="group_id must be DEV or PROD")


def _save_results(group_id: str, payload: dict) -> None:
    if group_id.upper() == "DEV":
        save_dev_results(payload)
    elif group_id.upper() == "PROD":
        save_prod_results(payload)
    else:
        raise HTTPException(status_code=400, detail="group_id must be DEV or PROD")


@app.on_event("startup")
def startup() -> None:
    ensure_directories()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_configured": bool(os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")),
        "model_mode": "local",
        "model": os.getenv("LLM_MODEL", "qwen/qwen3-4b-2507"),
        "model_base_url": os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1"),
    }


@app.get("/api/checklist", response_model=ChecklistConfig)
def get_checklist() -> ChecklistConfig:
    return ChecklistConfig.model_validate(load_checklist())


@app.put("/api/checklist", response_model=ChecklistConfig)
def update_checklist(payload: ChecklistConfig) -> ChecklistConfig:
    save_checklist(payload.model_dump())
    return payload


@app.post("/api/datasets/import")
def import_dataset(payload: OrganizerResponse) -> dict:
    if not payload.isSuccess:
        raise HTTPException(status_code=400, detail=payload.error or "Organizer API returned an error")
    records = payload.data.get("records")
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="data.records must be an array")
    conversations = [Conversation.model_validate(record) for record in records]
    ids = [item.conversation_id for item in conversations]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Duplicate conversation_id")
    group_id = str(payload.data.get("dataset_group_id", "DEV")).upper()
    if group_id not in {"DEV", "PROD"}:
        raise HTTPException(status_code=400, detail="dataset_group_id must be DEV or PROD")
    normalized = {
        "dataset_group_id": group_id,
        "total_records": len(conversations),
        "records": [item.model_dump() for item in conversations],
    }
    if group_id == "DEV":
        save_dev_dataset(normalized)
    else:
        save_prod_dataset(normalized)
    return {"dataset_group_id": group_id, "total_records": len(conversations)}


@app.get("/api/conversations")
def get_conversations(group_id: Literal["DEV", "PROD"] = "DEV") -> list[dict]:
    return _dataset(group_id).get("records", [])


@app.get("/api/conversations/demo")
def get_demo_conversation() -> dict:
    return {"source": "demonstration", "conversation": DEMO_CONVERSATION.model_dump()}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, group_id: Literal["DEV", "PROD"] = "DEV") -> dict:
    for record in _dataset(group_id).get("records", []):
        if record.get("conversation_id") == conversation_id:
            return record
    raise HTTPException(status_code=404, detail="Conversation not found")


@app.post("/api/evaluations/{conversation_id}", response_model=EvaluationResult | ErrorResult)
async def evaluate_conversation(
    conversation_id: str, group_id: Literal["DEV", "PROD"] = "DEV"
) -> EvaluationResult | ErrorResult:
    conversation = Conversation.model_validate(get_conversation(conversation_id, group_id))
    checklist = ChecklistConfig.model_validate(load_checklist())
    try:
        result = await OpenAICompatibleEvaluator().evaluate(conversation, checklist)
    except Exception as error:
        result = ErrorResult(conversation_id=conversation_id, error=str(error))
    results_file = _results(group_id)
    results = [item for item in results_file.get("results", []) if item.get("conversation_id") != conversation_id]
    results.append(result.model_dump())
    results_file.update({
        "schema_version": "1.0",
        "team_name": os.getenv("CQA_TEAM_NAME", ""),
        "model": {"mode": "local", "name": os.getenv("LLM_MODEL", "qwen/qwen3-4b-2507")},
        "results": results,
    })
    _save_results(group_id, results_file)
    return result


@app.get("/api/results/{group_id}")
def get_results(group_id: Literal["DEV", "PROD"] = "DEV") -> dict:
    return _results(group_id)


@app.get("/api/results/{group_id}/validate")
def validate_results(group_id: Literal["DEV", "PROD"] = "DEV") -> dict:
    dataset = _dataset(group_id)
    results = _results(group_id).get("results", [])
    dataset_ids = [item["conversation_id"] for item in dataset.get("records", [])]
    result_ids = [item.get("conversation_id") for item in results]
    errors = []
    if len(result_ids) != len(set(result_ids)):
        errors.append("duplicate conversation_id in results")
    missing = sorted(set(dataset_ids) - set(result_ids))
    if missing:
        errors.append(f"missing results: {', '.join(missing)}")
    extra = sorted(set(result_ids) - set(dataset_ids))
    if extra:
        errors.append(f"results not present in dataset: {', '.join(extra)}")
    for item in results:
        if item.get("status") == "ok":
            ids = [criterion.get("criterion_id") for criterion in item.get("criteria", [])]
            if ids != ["contact", "discovery", "identification", "consultation", "empathy", "dialogue", "closure", "critical"]:
                errors.append(f"invalid criteria for {item.get('conversation_id')}")
        elif item.get("status") != "error":
            errors.append(f"invalid status for {item.get('conversation_id')}")
    return {"valid": not errors, "group_id": group_id, "total": len(results), "errors": errors}


@app.post("/api/evaluations/recalculate", response_model=EvaluationResult)
def recalculate_evaluation(base_result: EvaluationResult, decision: ReviewerDecision | None = None) -> EvaluationResult:
    checklist = ChecklistConfig.model_validate(load_checklist())
    return recalculate_result(base_result, checklist, decision)


@app.get("/api/appeals")
def get_appeals() -> list[dict]:
    return load_appeals()


@app.post("/api/appeals", response_model=Appeal)
def create_appeal(appeal: Appeal) -> Appeal:
    current = load_appeals()
    current.append(appeal.model_dump())
    save_appeals(current)
    return appeal


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
