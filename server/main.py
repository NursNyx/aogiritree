from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .checklist import ChecklistConfig
from .database import ensure_directories, load_appeals, load_checklist, save_appeals, save_checklist
from .evaluator import Appeal, DEMO_CONVERSATION, EvaluationResult, ReviewerDecision, recalculate_result

app = FastAPI(title="Freedom Broker CQA Starter", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_directories()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/checklist", response_model=ChecklistConfig)
def get_checklist() -> ChecklistConfig:
    return ChecklistConfig.model_validate(load_checklist())


@app.put("/api/checklist", response_model=ChecklistConfig)
def update_checklist(payload: ChecklistConfig) -> ChecklistConfig:
    save_checklist(payload.model_dump())
    return payload


@app.get("/api/conversations/demo")
def get_demo_conversation() -> dict:
    return {
        "source": "demonstration",
        "conversation": DEMO_CONVERSATION.model_dump(),
    }


@app.post("/api/evaluations/recalculate", response_model=EvaluationResult)
def recalculate_evaluation(
    base_result: EvaluationResult,
    decision: ReviewerDecision | None = None,
) -> EvaluationResult:
    checklist = ChecklistConfig.model_validate(load_checklist())
    if not checklist.criteria:
        raise HTTPException(status_code=400, detail="Checklist is empty")
    return recalculate_result(base_result=base_result, checklist=checklist, decision=decision)


@app.get("/api/appeals")
def get_appeals() -> list[dict]:
    return load_appeals()


@app.post("/api/appeals", response_model=Appeal)
def create_appeal(appeal: Appeal) -> Appeal:
    current = load_appeals()
    current.append(appeal.model_dump())
    save_appeals(current)
    return appeal
