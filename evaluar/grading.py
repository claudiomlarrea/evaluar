"""EvaluAR - motor de corrección."""

from __future__ import annotations

import json
from typing import Any

from evaluar.utils import round_grade


def normalize_answer(value: str) -> str:
    return value.strip().upper()


def parse_stored_answer(value: str | dict[str, str]) -> str | dict[str, str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return value
        return value
    return value


def answers_match(student_answer: str, correct_answer: str | dict[str, str], qtype: str) -> bool:
    correct = parse_stored_answer(correct_answer)

    if qtype == "MATCHING":
        earned, status, _pair_total, _pair_correct = grade_matching_pairs(
            student_answer, correct, 1.0
        )
        return status == "correct" and earned > 0

    return normalize_answer(student_answer) == normalize_answer(str(correct))


def grade_matching_pairs(
    student_answer: str,
    correct_answer: str | dict[str, str],
    question_points: float,
) -> tuple[float, str, int, int]:
    """Crédito parcial: cada ítem vale question_points / N.

    Returns (earned_points, status, pair_total, pair_correct).
    status: correct | incorrect | unanswered
    """
    correct = parse_stored_answer(correct_answer)
    if not isinstance(correct, dict) or not correct:
        return 0.0, "unanswered", 0, 0

    pair_total = len(correct)
    try:
        student_obj = json.loads(student_answer) if student_answer.strip() else {}
    except json.JSONDecodeError:
        return 0.0, "unanswered", pair_total, 0
    if not isinstance(student_obj, dict):
        return 0.0, "unanswered", pair_total, 0

    answered_any = False
    pair_correct = 0
    for key, expected in correct.items():
        student_value = normalize_answer(str(student_obj.get(key, "")))
        if not student_value:
            continue
        answered_any = True
        if student_value == normalize_answer(str(expected)):
            pair_correct += 1

    if not answered_any:
        return 0.0, "unanswered", pair_total, 0

    earned = (pair_correct / pair_total) * float(question_points)
    if pair_correct == pair_total:
        return earned, "correct", pair_total, pair_correct
    return earned, "incorrect", pair_total, pair_correct


def parse_question(row: dict[str, Any]) -> dict[str, Any]:
    options = []
    try:
        options = json.loads(row["options"])
    except (json.JSONDecodeError, TypeError):
        options = []

    correct_answer: str | dict[str, str] = row["correct_answer"]
    try:
        parsed = json.loads(row["correct_answer"])
        if isinstance(parsed, dict):
            correct_answer = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "id": row["id"],
        "order": row["order"],
        "type": row["type"],
        "prompt": row["prompt"],
        "options": options,
        "correct_answer": correct_answer,
        "points": row["points"],
    }


def grade_submission(
    questions: list[dict[str, Any]],
    answers: dict[str, str],
    max_score: float,
) -> dict[str, Any]:
    total_points = 0.0
    earned_points = 0.0
    correct_count = 0
    wrong_count = 0
    unanswered_count = 0
    wrong_questions: list[int] = []
    incorrect_questions: list[int] = []
    unanswered_questions: list[int] = []

    for question in questions:
        parsed = parse_question(question) if "correct_answer" in question else question
        q_points = float(parsed["points"])
        total_points += q_points
        student_answer = answers.get(str(parsed["order"]), "").strip()
        order = int(parsed["order"])

        if parsed["type"] == "MATCHING":
            earned, status, _pair_total, _pair_correct = grade_matching_pairs(
                student_answer,
                parsed["correct_answer"],
                q_points,
            )
            earned_points += earned
            if status == "unanswered":
                unanswered_count += 1
                unanswered_questions.append(order)
                wrong_questions.append(order)
            elif status == "correct":
                correct_count += 1
            else:
                wrong_count += 1
                incorrect_questions.append(order)
                wrong_questions.append(order)
            continue

        if not student_answer:
            unanswered_count += 1
            unanswered_questions.append(order)
            wrong_questions.append(order)
            continue

        if answers_match(student_answer, parsed["correct_answer"], parsed["type"]):
            correct_count += 1
            earned_points += q_points
        else:
            wrong_count += 1
            incorrect_questions.append(order)
            wrong_questions.append(order)

    score = 0 if total_points == 0 else round_grade((earned_points / total_points) * max_score)

    return {
        "score": score,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "unanswered_count": unanswered_count,
        "wrong_questions": wrong_questions,
        "incorrect_questions": incorrect_questions,
        "unanswered_questions": unanswered_questions,
        "total_points": total_points,
        "earned_points": earned_points,
    }
