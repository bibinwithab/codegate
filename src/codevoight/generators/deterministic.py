from __future__ import annotations

import re
import uuid
from typing import List, Set
from codevoight.core.models import (
    QuizOption,
    QuizQuestion,
    QuizResult,
    QuizSubmission,
)
from codevoight.generators.base import BaseQuizEvaluator, BaseQuizGenerator


class DeterministicQuizGenerator(BaseQuizGenerator):
    """Zero-dependency, offline deterministic quiz generator based on AST/diff heuristics."""

    def generate_quiz(self, diff_text: str, description: str = "") -> List[QuizQuestion]:
        questions: List[QuizQuestion] = []
        files = self._extract_filenames(diff_text)
        added_lines, removed_lines = self._extract_added_removed(diff_text)
        symbols = self._extract_symbols(diff_text)

        # Question 1: File targeting
        if files:
            primary_file = files[0]
            options = [
                QuizOption(id="A", text=f"Modifies or introduces `{primary_file}`"),
                QuizOption(id="B", text=f"Deletes all tests in `tests/test_legacy.py`"),
                QuizOption(id="C", text=f"Replaces deployment manifests in `.k8s/`"),
                QuizOption(id="D", text=f"Only updates documentation in `docs/architecture.md`"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt=f"Which target file is modified in this staged diff?",
                    options=options,
                    correct_option_id="A",
                    explanation=f"The diff explicitly modifies `{primary_file}`.",
                )
            )

        # Question 2: Symbol / Function change
        if symbols:
            primary_symbol = symbols[0]
            options = [
                QuizOption(id="A", text=f"Introduces or modifies `{primary_symbol}`"),
                QuizOption(id="B", text=f"Deprecated `{primary_symbol}_legacy`"),
                QuizOption(id="C", text=f"Removes `{primary_symbol}` completely"),
                QuizOption(id="D", text="Does not touch any function or class definitions"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt="Which symbol or function definition is directly affected by this diff?",
                    options=options,
                    correct_option_id="A",
                    explanation=f"The diff contains changes to `{primary_symbol}`.",
                )
            )
        else:
            # Fallback based on added content length / keywords
            add_count = len(added_lines)
            rem_count = len(removed_lines)
            correct_summary = f"Adds ~{add_count} lines and removes ~{rem_count} lines"
            options = [
                QuizOption(id="A", text=correct_summary),
                QuizOption(id="B", text="Deletes the entire repository database"),
                QuizOption(id="C", text="Performs a full rollback to commit HEAD~10"),
                QuizOption(id="D", text="Changes only binary asset files"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt="What is the net line modification profile of this change?",
                    options=options,
                    correct_option_id="A",
                    explanation=f"The diff consists of {add_count} additions and {rem_count} deletions.",
                )
            )

        # Question 3: Semantic intent or condition
        has_error_handling = any(
            re.search(r"\b(raise|try|except|throw|catch|error|Err)\b", line, re.I)
            for line in added_lines
        )
        has_imports = any(
            re.search(r"^\s*(import|from|require|include)\b", line)
            for line in added_lines
        )

        if has_error_handling:
            options = [
                QuizOption(id="A", text="Adds error handling, exception guards, or validation"),
                QuizOption(id="B", text="Disables security assertions across all endpoints"),
                QuizOption(id="C", text="Swallows exceptions with silent pass statements"),
                QuizOption(id="D", text="Removes runtime input validation"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt="What validation or error handling behavior is added in this diff?",
                    options=options,
                    correct_option_id="A",
                    explanation="The diff introduces explicit exception handling or validation guards.",
                )
            )
        elif has_imports:
            options = [
                QuizOption(id="A", text="Imports or imports from additional modules/libraries"),
                QuizOption(id="B", text="Uninstalls all third-party dependencies"),
                QuizOption(id="C", text="Converts Python code to C++ bindings"),
                QuizOption(id="D", text="Disables external module resolution"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt="What dependency or module change is present in this diff?",
                    options=options,
                    correct_option_id="A",
                    explanation="New import statements are introduced in the staged change.",
                )
            )
        else:
            options = [
                QuizOption(id="A", text=f"Implements: {description or 'staged logic update'}"),
                QuizOption(id="B", text="Reverts all recent git commits"),
                QuizOption(id="C", text="Formats code with no functional edits"),
                QuizOption(id="D", text="Increments package version number only"),
            ]
            questions.append(
                QuizQuestion(
                    id=str(uuid.uuid4())[:8],
                    prompt="What is the primary stated intent of this change?",
                    options=options,
                    correct_option_id="A",
                    explanation="Reflects the staged change intent.",
                )
            )

        return questions

    def _extract_filenames(self, diff_text: str) -> List[str]:
        files: List[str] = []
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                files.append(line[6:].strip())
            elif line.startswith("--- a/") and line[6:].strip() not in files:
                f = line[6:].strip()
                if f != "/dev/null":
                    files.append(f)
        return list(dict.fromkeys(files))

    def _extract_added_removed(self, diff_text: str) -> tuple[List[str], List[str]]:
        added = []
        removed = []
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:].strip())
            elif line.startswith("-") and not line.startswith("---"):
                removed.append(line[1:].strip())
        return added, removed

    def _extract_symbols(self, diff_text: str) -> List[str]:
        symbols: Set[str] = set()
        pattern = re.compile(r"^\+\s*(?:async\s+)?(?:def|class|function|const|let|var)\s+([a-zA-Z0-9_]+)")
        for line in diff_text.splitlines():
            match = pattern.search(line)
            if match:
                symbols.add(match.group(1))
        return sorted(list(symbols))


class DeterministicQuizEvaluator(BaseQuizEvaluator):
    """Deterministic grading engine enforcing 100% threshold by default."""

    def __init__(self, passing_score: float = 1.0):
        self.passing_score = passing_score

    def evaluate(self, submission: QuizSubmission, questions: List[QuizQuestion]) -> QuizResult:
        if not questions:
            return QuizResult(
                session_id=submission.session_id,
                passed=True,
                score=1.0,
                total=0,
                correct=0,
                feedback=["No questions required for this diff."],
            )

        total = len(questions)
        correct = 0
        feedback: List[str] = []

        for q in questions:
            chosen = submission.answers.get(q.id)
            if chosen == q.correct_option_id:
                correct += 1
                feedback.append(f"Question '{q.prompt}': Correct!")
            else:
                feedback.append(
                    f"Question '{q.prompt}': Incorrect. You answered {chosen}, "
                    f"expected {q.correct_option_id}. {q.explanation}"
                )

        score = correct / total
        passed = score >= self.passing_score

        return QuizResult(
            session_id=submission.session_id,
            passed=passed,
            score=score,
            total=total,
            correct=correct,
            feedback=feedback,
        )
