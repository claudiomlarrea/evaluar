"""Construcción de preguntas desde el asistente docente."""

from __future__ import annotations

import json
from typing import Any

from evaluar.answer_parser import letters_for_count

TYPE_CHOICES = {
    "Opción múltiple": "MULTIPLE_CHOICE",
    "Verdadero / Falso": "TRUE_FALSE",
    "Emparejamiento": "MATCHING",
}

TYPE_LABELS = {value: label for label, value in TYPE_CHOICES.items()}


def default_question_draft(order: int) -> dict[str, Any]:
    return {
        "order": order,
        "type": "MULTIPLE_CHOICE",
        "option_count": 5,
        "item_count": 3,
        "target_count": 6,
        "mc_answer": "A",
        "vf_answer": "V",
        "matching_items": ["a", "b", "c"],
        "matching_answers": {"a": "A", "b": "B", "c": "C"},
        "points": 1.0,
    }


def item_labels(count: int) -> list[str]:
    return [chr(ord("a") + index) for index in range(count)]


def build_question(draft: dict[str, Any]) -> dict[str, Any]:
    order = int(draft["order"])
    qtype = draft["type"]
    points = float(draft.get("points", 1))
    if points <= 0:
        raise ValueError(f"Pregunta {order}: el puntaje debe ser mayor a cero.")

    if qtype == "TRUE_FALSE":
        answer = str(draft.get("vf_answer", "V")).upper()
        if answer not in {"V", "F"}:
            raise ValueError(f"Pregunta {order}: respuesta V/F inválida.")
        return {
            "order": order,
            "type": "TRUE_FALSE",
            "prompt": None,
            "options": ["V", "F"],
            "correct_answer": answer,
            "points": points,
        }

    if qtype == "MULTIPLE_CHOICE":
        count = int(draft.get("option_count", 5))
        options = letters_for_count(count)
        answer = str(draft.get("mc_answer", "A")).upper()
        if answer not in options:
            raise ValueError(
                f"Pregunta {order}: la respuesta '{answer}' no está entre las {count} opciones."
            )
        return {
            "order": order,
            "type": "MULTIPLE_CHOICE",
            "prompt": None,
            "options": options,
            "correct_answer": answer,
            "points": points,
        }

    if qtype == "MATCHING":
        target_count = int(draft.get("target_count", 6))
        item_count = int(draft.get("item_count", 3))
        targets = letters_for_count(target_count)
        labels = item_labels(item_count)
        answers = draft.get("matching_answers") or {}
        pairs: dict[str, str] = {}

        for label in labels:
            chosen = str(answers.get(label, "")).upper()
            if not chosen or chosen not in targets:
                raise ValueError(
                    f"Pregunta {order}: definí la respuesta correcta del ítem '{label}'."
                )
            pairs[label] = chosen

        return {
            "order": order,
            "type": "MATCHING",
            "prompt": None,
            "options": {
                "items": [{"left": label, "right": ""} for label in labels],
                "targets": targets,
            },
            "correct_answer": pairs,
            "points": points,
        }

    raise ValueError(f"Pregunta {order}: tipo desconocido.")


def build_all_questions(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_question(draft) for draft in drafts]


def _parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def question_row_to_draft(question: dict[str, Any]) -> dict[str, Any]:
    """Convierte una fila de la base al formato del asistente docente."""
    order = int(question["order"])
    qtype = question["type"]
    draft: dict[str, Any] = {
        "order": order,
        "type": qtype,
        "points": float(question.get("points") or 1),
    }
    options_raw = _parse_json_field(question.get("options"), [])
    correct = question.get("correct_answer")
    if qtype == "MATCHING":
        correct = _parse_json_field(correct, {})
    else:
        correct = str(correct or "").strip().upper()

    if qtype == "MULTIPLE_CHOICE":
        options = options_raw if isinstance(options_raw, list) else []
        draft["option_count"] = len(options) or 5
        draft["mc_answer"] = correct or "A"
    elif qtype == "TRUE_FALSE":
        draft["vf_answer"] = correct if correct in {"V", "F"} else "V"
    elif qtype == "MATCHING":
        opts = options_raw if isinstance(options_raw, dict) else {}
        targets = opts.get("targets", [])
        items = opts.get("items", [])
        draft["target_count"] = len(targets) or 6
        draft["item_count"] = len(items) or 3
        labels = [
            str(item.get("left", "")).lower()
            for item in items
            if item.get("left")
        ]
        if not labels:
            labels = item_labels(draft["item_count"])
        correct_map = correct if isinstance(correct, dict) else {}
        draft["matching_answers"] = {
            label: str(
                correct_map.get(label)
                or correct_map.get(label.upper())
                or "A"
            ).upper()
            for label in labels
        }
    return draft


def drafts_from_exam_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        question_row_to_draft(question)
        for question in sorted(questions, key=lambda row: int(row["order"]))
    ]
