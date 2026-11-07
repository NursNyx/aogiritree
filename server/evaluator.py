from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .checklist import ChecklistConfig
from .scoring import calculate_weighted_score, extract_critical_flag


class TranscriptTurn(BaseModel):
    timestamp: str
    speaker: str
    text: str


class Conversation(BaseModel):
    conversation_id: str
    channel: str
    language: Literal["ru", "kk", "en"]
    transcript: List[TranscriptTurn]
    audio_url: Optional[str] = None


class CriterionEvaluation(BaseModel):
    criterion_id: str
    value: bool | int | None
    rationale: str = ""
    evidence_turns: List[int] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    conversation_id: str
    criterion_results: List[CriterionEvaluation]
    final_score: Optional[float] = None
    critical_flag: bool = False
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Appeal(BaseModel):
    appeal_id: str
    conversation_id: str
    note: str
    reviewer_decision: Optional[str] = None


class ReviewerDecision(BaseModel):
    updates: List[CriterionEvaluation] = Field(default_factory=list)
    decision_note: str = ""


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(
        self, conversation: Conversation, checklist: ChecklistConfig
    ) -> EvaluationResult:
        """Implement real provider-backed evaluation in future iterations."""


class NotImplementedEvaluator(BaseEvaluator):
    def evaluate(
        self, conversation: Conversation, checklist: ChecklistConfig
    ) -> EvaluationResult:
        raise NotImplementedError(
            "AI evaluator provider is not configured yet. "
            "Use manual reviewer flow or integrate provider implementation."
        )


def recalculate_result(
    base_result: EvaluationResult,
    checklist: ChecklistConfig,
    decision: Optional[ReviewerDecision] = None,
) -> EvaluationResult:
    merged: Dict[str, CriterionEvaluation] = {
        item.criterion_id: item for item in base_result.criterion_results
    }

    if decision:
        for update in decision.updates:
            merged[update.criterion_id] = update

    merged_list = list(merged.values())
    value_map = {item.criterion_id: item.value for item in merged_list}

    return EvaluationResult(
        conversation_id=base_result.conversation_id,
        criterion_results=merged_list,
        final_score=calculate_weighted_score(checklist.criteria, value_map),
        critical_flag=extract_critical_flag(value_map),
    )


# Demonstration-only conversation scaffold. This is not an evaluation result.
DEMO_CONVERSATION = Conversation(
    conversation_id="demo-001",
    channel="chat",
    language="en",
    transcript=[
        TranscriptTurn(timestamp="00:00:01", speaker="agent", text="Hello!"),
        TranscriptTurn(
            timestamp="00:00:03", speaker="client", text="I need account help."
        ),
    ],
    audio_url=None,
)
