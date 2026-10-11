from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from codegate.core.models import QuizQuestion, QuizResult, QuizSubmission


class BaseQuizGenerator(ABC):
    @abstractmethod
    def generate_quiz(self, diff_text: str, description: str = "") -> List[QuizQuestion]:
        """Generate comprehension questions based on the diff and optional description."""
        pass


class BaseQuizEvaluator(ABC):
    @abstractmethod
    def evaluate(self, submission: QuizSubmission, questions: List[QuizQuestion]) -> QuizResult:
        """Evaluate developer answers and determine pass/fail with feedback."""
        pass
