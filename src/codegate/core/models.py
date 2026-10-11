from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    PENDING_QUIZ = "PENDING_QUIZ"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class StagedFile(BaseModel):
    file_path: str
    new_content: str
    old_content: Optional[str] = None
    is_new: bool = False
    is_deleted: bool = False


class QuizOption(BaseModel):
    id: str  # "A", "B", "C", "D"
    text: str


class QuizQuestion(BaseModel):
    id: str
    prompt: str
    options: List[QuizOption]
    correct_option_id: str
    explanation: str


class QuizSubmission(BaseModel):
    session_id: str
    answers: dict[str, str]  # question_id -> chosen_option_id


class QuizResult(BaseModel):
    session_id: str
    passed: bool
    score: float
    total: int
    correct: int
    feedback: List[str] = Field(default_factory=list)
    capability_token: Optional[str] = None


class CapabilityToken(BaseModel):
    session_id: str
    diff_hash: str
    timestamp: int
    signature: str

    def serialize(self) -> str:
        return f"{self.session_id}:{self.diff_hash}:{self.timestamp}:{self.signature}"

    @classmethod
    def parse(cls, raw: str) -> CapabilityToken:
        parts = raw.split(":")
        if len(parts) != 4:
            raise ValueError("Malformed capability token format")
        return cls(
            session_id=parts[0],
            diff_hash=parts[1],
            timestamp=int(parts[2]),
            signature=parts[3],
        )


class StagedSession(BaseModel):
    session_id: str
    diff_text: str
    diff_hash: str
    description: str = ""
    status: SessionStatus = SessionStatus.PENDING_QUIZ
    created_at: float
    expires_at: float
    capability_token: Optional[str] = None
