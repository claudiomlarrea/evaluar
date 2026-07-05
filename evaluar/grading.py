"""EvaluAR - motor de corrección."""

from __future__ import annotations

import json
from typing import Any


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
        if not isinstance(correct, dict):
            return False
        try:
            student_obj = json.loads(student_answer)
        except json.JSONDecodeError:
            return False
        if not isinstance(student_obj, dict):
            return False
        if not correct:
            return False
        return all(
            normalize_answer(str(student_obj.get(key, "")))
            == normalize_answer(str(correct[key]))
            for key in correct
        )

    return normalize_answer(student_answer) == normalize_answer(str(correct))


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

    for question in questions:
        parsed = parse_question(question) if "correct_answer" in question else question
        total_points += float(parsed["points"])
        student_answer = answers.get(str(parsed["order"]), "").strip()

        if not student_answer:
            unanswered_count += 1
            wrong_questions.append(int(parsed["order"]))
            continue

        if answers_match(student_answer, parsed["correct_answer"], parsed["type"]):
            correct_count += 1
            earned_points += float(parsed["points"])
        else:
            wrong_count += 1
            wrong_questions.append(int(parsed["order"]))

    score = 0.0 if total_points == 0 else round((earned_points / total_points) * max_score, 2)

    return {
        "score": score,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "unanswered_count": unanswered_count,
        "wrong_questions": wrong_questions,
        "total_points": total_points,
        "earned_points": earned_points,
    }
