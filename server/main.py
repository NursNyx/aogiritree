from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import httpx
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
    Appeal, AppealUpdate, Conversation, CRITERION_IDS, DEMO_CONVERSATION,
    ErrorResult, EvaluationResult, OpenAICompatibleEvaluator, ReviewerDecision,
    CriterionEvaluation, recalculate_result,
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


@app.get("/api/model/status")
async def model_status() -> dict:
    base_url = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "qwen/qwen3-4b-2507")
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{base_url}/models")
        return {"reachable": response.is_success, "model": model, "base_url": base_url}
    except Exception as error:
        return {"reachable": False, "model": model, "base_url": base_url, "error": str(error)}


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
            score = item.get("score") or {}
            if score.get("final_score") is not None and not 0 <= score["final_score"] <= 100:
                errors.append(f"invalid score for {item.get('conversation_id')}")
        elif item.get("status") != "error":
            errors.append(f"invalid status for {item.get('conversation_id')}")
        elif not item.get("error") or item.get("criteria") != [] or item.get("score") is not None:
            errors.append(f"invalid error result for {item.get('conversation_id')}")
    return {
        "valid": not errors,
        "group_id": group_id,
        "total": len(results),
        "ok": sum(item.get("status") == "ok" for item in results),
        "error": sum(item.get("status") == "error" for item in results),
        "pending": max(0, len(dataset_ids) - len(results)),
        "errors": errors,
    }


@app.post("/api/evaluations/recalculate", response_model=EvaluationResult)
def recalculate_evaluation(base_result: EvaluationResult, decision: ReviewerDecision | None = None) -> EvaluationResult:
    checklist = ChecklistConfig.model_validate(load_checklist())
    return recalculate_result(base_result, checklist, decision)


@app.get("/api/appeals")
def get_appeals(status: Literal["open", "confirmed", "changed"] | None = None) -> list[dict]:
    appeals = load_appeals()
    if status:
        appeals = [appeal for appeal in appeals if appeal.get("status") == status]
    return appeals


@app.post("/api/appeals", response_model=Appeal)
def create_appeal(appeal: Appeal) -> Appeal:
    current = load_appeals()
    if any(item.get("appeal_id") == appeal.appeal_id for item in current):
        raise HTTPException(status_code=409, detail="appeal_id already exists")
    current.append(appeal.model_dump())
    save_appeals(current)
    return appeal


@app.put("/api/appeals/{appeal_id}")
def resolve_appeal(
    appeal_id: str,
    payload: AppealUpdate,
    group_id: Literal["DEV", "PROD"] = "DEV",
) -> dict[str, Any]:
    appeals = load_appeals()
    appeal = next((item for item in appeals if item.get("appeal_id") == appeal_id), None)
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found")
    if payload.status == "changed" and "reviewer_value" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="reviewer_value is required when changing a result")
    result_file = _results(group_id)
    result_item = next(
        (item for item in result_file.get("results", [])
         if item.get("conversation_id") == appeal.get("conversation_id")),
        None,
    )
    if result_item is None:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    updated_result: EvaluationResult | None = None
    if payload.status == "changed":
        if result_item.get("status") != "ok":
            raise HTTPException(status_code=400, detail="Only successful evaluations can be recalculated")
        base_result = EvaluationResult.model_validate(result_item)
        current = next(
            (item for item in base_result.criteria if item.criterion_id == appeal.get("criterion_id")),
            None,
        )
        if current is None or appeal.get("criterion_id") not in CRITERION_IDS:
            raise HTTPException(status_code=400, detail="Unknown criterion_id")
        update = CriterionEvaluation(
            criterion_id=current.criterion_id,
            value=payload.reviewer_value,
            rationale=payload.reviewer_decision or "Оценка изменена проверяющим.",
            evidence_turns=current.evidence_turns,
        )
        updated_result = recalculate_result(
            base_result,
            ChecklistConfig.model_validate(load_checklist()),
            ReviewerDecision(updates=[update], decision_note=payload.reviewer_decision),
        )
        result_file["results"] = [
            updated_result.model_dump()
            if item.get("conversation_id") == appeal.get("conversation_id") else item
            for item in result_file.get("results", [])
        ]
        _save_results(group_id, result_file)
    appeal.update({
        "status": payload.status,
        "reviewer_decision": payload.reviewer_decision,
        "reviewer_value": payload.reviewer_value,
    })
    save_appeals(appeals)
    return {"appeal": appeal, "result": updated_result.model_dump() if updated_result else result_item}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
