from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from .checklist import ChecklistConfig
from .scoring import calculate_weighted_score, extract_critical_flag


class TranscriptTurn(BaseModel):
    timestamp: str
    speaker: Literal["client", "operator", "bot", "system"]
    text: str


class Conversation(BaseModel):
    conversation_id: str
    channel: Literal["agent chat", "voice call"]
    language: Literal["RU", "KZ", "EN"]
    transcript: list[TranscriptTurn]
    audio_url: Optional[str] = None


class CriterionEvaluation(BaseModel):
    criterion_id: str
    value: bool | int | None
    rationale: str = Field(min_length=1)
    evidence_turns: list[int] = Field(default_factory=list)


class ScoreResult(BaseModel):
    final_score: Optional[float]
    critical_flag: bool


class EvaluationResult(BaseModel):
    conversation_id: str
    status: Literal["ok"] = "ok"
    criteria: list[CriterionEvaluation]
    score: ScoreResult


class ErrorResult(BaseModel):
    conversation_id: str
    status: Literal["error"] = "error"
    criteria: list = Field(default_factory=list)
    score: None = None
    error: str


class Appeal(BaseModel):
    appeal_id: str
    conversation_id: str
    criterion_id: str
    note: str
    status: Literal["open", "confirmed", "changed"] = "open"
    reviewer_decision: Optional[str] = None
    reviewer_value: bool | int | None = None


class AppealUpdate(BaseModel):
    status: Literal["open", "confirmed", "changed"]
    reviewer_decision: str = ""
    reviewer_value: bool | int | None = None


class ReviewerDecision(BaseModel):
    updates: list[CriterionEvaluation] = Field(default_factory=list)
    decision_note: str = ""


CRITERION_IDS = [
    "contact", "discovery", "identification", "consultation",
    "empathy", "dialogue", "closure", "critical",
]


STRONG_RESOLUTION_PATTERNS = (
    r"\b(наш[её]л|нашла|понял|поняла|разобрался|разобралась|получилось|теперь понятно)\b",
    r"\b(found it|got it|understood|that worked|it works now|makes sense now)\b",
    r"\b(таптым|түсіндім|түсінікті болды|болды, таптым|шықты)\b",
)

GOODBYE_PATTERNS = (
    r"\b(до свидания|всего доброго|хорошего (?:дня|вечера)|будьте здоровы)\b",
    r"\b(goodbye|have a (?:good|great|nice) (?:day|evening)|take care)\b",
    r"\b(сау болыңыз|күніңіз сәтті өтсін|қайырлы күн)\b",
)
HELP_OR_SUMMARY_PATTERNS = (
    r"\b(могу ли я ещ[её]|чем[- ](?:то )?ещ[её] помочь|остались ли вопросы|подведу итог|итак|резюмир)\b",
    r"\b(anything else|further assistance|any other questions|to summarize|in summary|we(?:'|’)ll follow up)\b",
    r"\b(тағы.*көмек|басқа сұрақ|қорытынды|хабарласамыз|жауап береміз)\b",
)


def _extract_json(text: str) -> dict:
    """Accept plain JSON and the occasional fenced response from small local models."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _apply_objective_calibration(
    criteria: list[CriterionEvaluation], conversation: Conversation,
) -> list[CriterionEvaluation]:
    """Correct only high-confidence, transcript-verifiable misses from a small LLM."""
    by_id = {item.criterion_id: item for item in criteria}

    discovery = by_id["discovery"]
    discovery_reason = discovery.rationale.lower()
    sufficient_markers = (
        "already contained sufficient", "already contained enough", "enough information",
        "уже содержал достат", "уже содержали достат", "информации было достаточно",
        "не означает, что информация была недостаточной", "запрос был избыточным",
        "ақпарат жеткілікті", "жеткілікті ақпарат",
    )
    if discovery.value is False and any(marker in discovery_reason for marker in sufficient_markers):
        discovery.value = None
        discovery.rationale = {
            "RU": "До подключения оператора в обращении уже было достаточно данных для точного ответа; уточнение не требовалось.",
            "KZ": "Оператор қосылғанға дейін нақты жауап беруге жеткілікті ақпарат болды; қосымша нақтылау қажет емес.",
            "EN": "The pre-operator context already contained enough information for an accurate answer; clarification was not required.",
        }[conversation.language]

    empathy = by_id["empathy"]
    empathy_reason = empathy.rationale.lower()
    no_negative_markers = (
        "did not express any frustration", "did not express frustration", "no negative emotion",
        "не выражал раздраж", "не выражал негатив", "не проявил негатив",
        "жағымсыз эмоция білдірмеді", "реніш білдірмеді",
    )
    if empathy.value is False and any(marker in empathy_reason for marker in no_negative_markers):
        empathy.value = True
        empathy.rationale = {
            "RU": "Клиент не выражал негативных эмоций; оператор общался вежливо и профессионально.",
            "KZ": "Клиент жағымсыз эмоция білдірмеді; оператор сыпайы әрі кәсіби сөйлесті.",
            "EN": "The client expressed no negative emotion; the operator remained polite and professional.",
        }[conversation.language]

    closure = by_id["closure"]
    operator_text = " ".join(
        turn.text for turn in conversation.transcript if turn.speaker == "operator"
    )
    has_goodbye = any(re.search(pattern, operator_text, re.IGNORECASE) for pattern in GOODBYE_PATTERNS)
    has_help_or_summary = any(
        re.search(pattern, operator_text, re.IGNORECASE) for pattern in HELP_OR_SUMMARY_PATTERNS
    )
    if closure.value is True and not (has_goodbye and has_help_or_summary):
        closure.value = False
        closure.rationale = {
            "RU": "Оператор попрощался, но не подвёл итог и не предложил дополнительную помощь.",
            "KZ": "Оператор қоштасты, бірақ қорытынды жасамады және қосымша көмек ұсынбады.",
            "EN": "The operator said goodbye but did not summarize the outcome or offer further help.",
        }[conversation.language]
    consultation = by_id["consultation"]
    if isinstance(consultation.value, int) and consultation.value < 20:
        operator_turns = [
            index for index, turn in enumerate(conversation.transcript, start=1)
            if turn.speaker == "operator" and turn.text.strip()
        ]
        confirmations = [
            index for index, turn in enumerate(conversation.transcript, start=1)
            if turn.speaker == "client"
            and any(re.search(pattern, turn.text, re.IGNORECASE) for pattern in STRONG_RESOLUTION_PATTERNS)
        ]
        if operator_turns and confirmations:
            confirmation_turn = confirmations[-1]
            preceding_operator = [turn for turn in operator_turns if turn < confirmation_turn]
            later_client_questions = [
                turn.text for turn in conversation.transcript[confirmation_turn:]
                if turn.speaker == "client" and "?" in turn.text
            ]
            if preceding_operator and not later_client_questions:
                consultation.value = 20
                consultation.rationale = {
                    "RU": "Клиент явно подтвердил, что решение сработало; существенных вопросов не осталось.",
                    "KZ": "Клиент шешімнің көмектескенін нақты растады; маңызды сұрақтар қалмады.",
                    "EN": "The client explicitly confirmed that the solution worked; no material question remained.",
                }[conversation.language]
                consultation.evidence_turns = [preceding_operator[-1], confirmation_turn]
    return criteria


def _validate_criteria(criteria: list[CriterionEvaluation], conversation: Conversation) -> None:
    if [item.criterion_id for item in criteria] != CRITERION_IDS:
        raise ValueError("Model result must contain all eight criteria in the required order")
    allowed = {
        "contact": {True, False}, "discovery": {True, False, None},
        "identification": {True, False, None}, "consultation": {0, 5, 10, 15, 20, None},
        "empathy": {True, False}, "dialogue": {0, 4, 7, 10},
        "closure": {True, False, None}, "critical": {True, False},
    }
    for item in criteria:
        if item.value not in allowed[item.criterion_id]:
            raise ValueError(f"Invalid value for {item.criterion_id}: {item.value!r}")
        if any(turn < 1 or turn > len(conversation.transcript) for turn in item.evidence_turns):
            raise ValueError(f"Invalid evidence_turns for {item.criterion_id}")


def recalculate_result(
    base_result: EvaluationResult,
    checklist: ChecklistConfig,
    decision: Optional[ReviewerDecision] = None,
) -> EvaluationResult:
    merged = {item.criterion_id: item for item in base_result.criteria}
    if decision:
        for update in decision.updates:
            merged[update.criterion_id] = update
    criteria = [merged[criterion_id] for criterion_id in CRITERION_IDS]
    values = {item.criterion_id: item.value for item in criteria}
    return EvaluationResult(
        conversation_id=base_result.conversation_id,
        criteria=criteria,
        score=ScoreResult(
            final_score=calculate_weighted_score(checklist.criteria, values),
            critical_flag=extract_critical_flag(values),
        ),
    )


class OpenAICompatibleEvaluator:
    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "qwen/qwen3-4b-2507")

    async def evaluate(self, conversation: Conversation, checklist: ChecklistConfig) -> EvaluationResult:
        transcript = "\n".join(
            f"{index}. [{turn.speaker}] {turn.text}"
            for index, turn in enumerate(conversation.transcript, start=1)
        )
        system_prompt = """You are a strict multilingual conversation quality auditor for a broker support service.
Evaluate ONLY the human operator. Bot behavior never earns or loses operator points. Client, bot and system turns are context and may support N/A, but rationales must describe operator behavior.

Rules:
1 contact (boolean): true only if the operator greeted the client in the client's language AND introduced themself in the operator's first response.
2 discovery (boolean|null): true if the operator used known details and clarified information genuinely missing before answering. null when the request plus pre-operator context already contained enough to give the correct answer. Do not require unnecessary clarification. false only when missing information made a reliable answer impossible but the operator guessed or skipped clarification.
3 identification (boolean|null): true only when identity was confirmed BEFORE account data disclosure or a protected action. A system turn explicitly confirming identity is valid evidence. Merely mentioning a name, account, profile, full name, or where data is displayed is NOT identification. null when the request did not require identity verification. false when verification was required but not completed before the protected action.
4 consultation (0|5|10|15|20|null): 20 all material questions solved or a correct next step was given; 15 main issue solved with a real secondary detail omitted; 10 only part solved and a material question remains; 5 generic hint with unclear action; 0 no substantive answer or key recommendation wrong; null only when the chat ended before the client stated a request. A client confirmation such as "found it", "understood", or equivalent is strong outcome evidence that the request was solved; do not invent hypothetical missing details after such confirmation.
5 empathy (boolean): true when the operator is polite and, if the client expressed frustration or inconvenience, reacted to that specific issue. When the client expressed no negative emotion, ordinary professional politeness is enough for true. Do not use client politeness as operator evidence.
6 dialogue (0|4|7|10): judge the human-operator segment, not bot delays before escalation. 10 clear and coherent and any wait caused by the operator was announced; 7 one actual noticeable issue but understandable; 4 client had to ask the human operator again because of the operator's wording/order; 0 incoherent or contradictory. Do not penalize the operator for questions repeated only before the operator joined.
7 closure (boolean|null): true when the operator summarized or offered further help AND said goodbye; null only if the chat ended before the operator had an opportunity to close; otherwise false.
8 critical (boolean): true only for an insult, an offer of a paid private service outside the company, or disclosure of confidential information.

Return one JSON object with a criteria array containing exactly these IDs in this order: contact, discovery, identification, consultation, empathy, dialogue, closure, critical. Each item has criterion_id, value, a concise rationale in the conversation language, and evidence_turns. Number turns from 1 over the complete original transcript. Cite the smallest relevant set of turns. For omitted actions cite the location where the action was expected. For critical=false an empty evidence_turns array is allowed. Null means N/A and must be justified."""
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1200,
            "response_format": {"type": "text"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Checklist: {checklist.model_dump_json()}\nLanguage: {conversation.language}\nChannel: {conversation.channel}\nTranscript:\n{transcript}"},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        if response.is_error:
            raise RuntimeError(f"Local model returned {response.status_code}: {response.text}")
        completion = response.json()
        parsed = _extract_json(completion["choices"][0]["message"]["content"])
        criteria = [CriterionEvaluation.model_validate(item) for item in parsed["criteria"]]
        _validate_criteria(criteria, conversation)
        criteria = _apply_objective_calibration(criteria, conversation)
        values = {item.criterion_id: item.value for item in criteria}
        return EvaluationResult(
            conversation_id=conversation.conversation_id,
            criteria=criteria,
            score=ScoreResult(
                final_score=calculate_weighted_score(checklist.criteria, values),
                critical_flag=extract_critical_flag(values),
            ),
        )


DEMO_CONVERSATION = Conversation(
    conversation_id="demo-001",
    channel="agent chat",
    language="EN",
    transcript=[
        TranscriptTurn(timestamp="00:01", speaker="operator", text="Hello, my name is Alex."),
        TranscriptTurn(timestamp="00:03", speaker="client", text="I need account help."),
    ],
)
