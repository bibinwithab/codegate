from __future__ import annotations

import os
from typing import List, Optional

from codevoight.core.models import QuizQuestion
from codevoight.generators.base import BaseQuizGenerator
from codevoight.generators.deterministic import DeterministicQuizGenerator


class LLMQuizGenerator(BaseQuizGenerator):
    """Pluggable LLM generator with automatic fallback to deterministic generator."""

    def __init__(self, fallback_generator: Optional[BaseQuizGenerator] = None):
        self.fallback = fallback_generator or DeterministicQuizGenerator()
        self.api_key = os.getenv("CODEVOIGHT_LLM_API_KEY") or os.getenv("QUIZGATE_LLM_API_KEY") or os.getenv("CODEGATE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")

    def generate_quiz(self, diff_text: str, description: str = "") -> List[QuizQuestion]:
        # If no LLM credentials provided or in offline/test mode, seamlessly use deterministic engine
        if not self.api_key:
            return self.fallback.generate_quiz(diff_text, description)

        try:
            # Pluggable LLM invocation hook
            # If external network call fails or is not configured, fallback gracefully
            return self._call_llm_api(diff_text, description)
        except Exception:
            return self.fallback.generate_quiz(diff_text, description)

    def _call_llm_api(self, diff_text: str, description: str = "") -> List[QuizQuestion]:
        # Placeholder for external LLM-as-a-judge provider integration
        # In base install, falls back safely to deterministic rules
        return self.fallback.generate_quiz(diff_text, description)
