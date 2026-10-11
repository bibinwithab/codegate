from codegate.core.models import QuizSubmission
from codegate.generators.deterministic import (
    DeterministicQuizEvaluator,
    DeterministicQuizGenerator,
)


def test_deterministic_generator_and_evaluator():
    diff_text = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,7 @@
 import os
+import hashlib
 
+def verify_password(plain, hashed):
+    if not plain:
+        raise ValueError("Empty password")
+    return True
"""
    generator = DeterministicQuizGenerator()
    questions = generator.generate_quiz(diff_text, description="Add password verification")

    assert len(questions) >= 2
    # Verify each question has valid choices
    for q in questions:
        assert len(q.options) == 4
        assert q.correct_option_id in ["A", "B", "C", "D"]

    evaluator = DeterministicQuizEvaluator(passing_score=1.0)

    # Perfect submission must pass
    correct_answers = {q.id: q.correct_option_id for q in questions}
    res_pass = evaluator.evaluate(
        QuizSubmission(session_id="sess-test", answers=correct_answers),
        questions,
    )
    assert res_pass.passed is True
    assert res_pass.score == 1.0

    # Incorrect submission must fail
    wrong_answers = {q.id: "B" if q.correct_option_id != "B" else "C" for q in questions}
    res_fail = evaluator.evaluate(
        QuizSubmission(session_id="sess-test", answers=wrong_answers),
        questions,
    )
    assert res_fail.passed is False
    assert res_fail.score == 0.0
    assert len(res_fail.feedback) == len(questions)
