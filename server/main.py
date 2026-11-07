from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .checklist import ChecklistConfig
from .database import (
    ensure_directories, load_appeals, load_checklist, load_dev_dataset,
    load_dev_results, save_appeals, save_checklist, save_dev_dataset, save_dev_results,
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


@app.on_event("startup")
def startup() -> None:
    ensure_directories()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_configured": True,
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
    normalized = {
        "dataset_group_id": payload.data.get("dataset_group_id", "DEV"),
        "total_records": len(conversations),
        "records": [item.model_dump() for item in conversations],
    }
    save_dev_dataset(normalized)
    return {"dataset_group_id": normalized["dataset_group_id"], "total_records": len(conversations)}


@app.get("/api/conversations")
def get_conversations() -> list[dict]:
    return load_dev_dataset().get("records", [])


@app.get("/api/conversations/demo")
def get_demo_conversation() -> dict:
    return {"source": "demonstration", "conversation": DEMO_CONVERSATION.model_dump()}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    for record in load_dev_dataset().get("records", []):
        if record.get("conversation_id") == conversation_id:
            return record
    raise HTTPException(status_code=404, detail="Conversation not found")


@app.post("/api/evaluations/{conversation_id}", response_model=EvaluationResult)
async def evaluate_conversation(conversation_id: str) -> EvaluationResult:
    conversation = Conversation.model_validate(get_conversation(conversation_id))
    checklist = ChecklistConfig.model_validate(load_checklist())
    try:
        result = await OpenAICompatibleEvaluator().evaluate(conversation, checklist)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    results_file = load_dev_results()
    results = [item for item in results_file.get("results", []) if item.get("conversation_id") != conversation_id]
    results.append(result.model_dump())
    results_file.update({
        "schema_version": "1.0",
        "model": {"mode": "local", "name": os.getenv("LLM_MODEL", "qwen/qwen3-4b-2507")},
        "results": results,
    })
    save_dev_results(results_file)
    return result


@app.get("/api/results/dev")
def get_dev_results() -> dict:
    return load_dev_results()


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


app.mount("/", StaticFiles(directory="web", html=True), name="web")
