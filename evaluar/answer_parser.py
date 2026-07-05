"""Parser de clave de respuestas con tipos mixtos."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_MC = ["A", "B", "C", "D", "E"]
DEFAULT_MATCH_TARGETS = list("ABCDEFGH")

LINE_PATTERN = re.compile(r"^\s*(?:(\d+)\s*(?:[:.)-]\s*|\s+))?(.+?)\s*$")
PAIR_PATTERN = re.compile(r"^\s*([a-zA-Z0-9]+)\s*(?:->|:|=)\s*([a-zA-Z0-9]+)\s*$")


class AnswerKeyError(ValueError):
    """Error al interpretar la clave de respuestas."""


def _normalize_token(value: str) -> str:
    return value.strip().upper()


def parse_matching_pairs(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for chunk in re.split(r"[,;]", raw):
        piece = chunk.strip()
        if not piece:
            continue
        match = PAIR_PATTERN.match(piece)
        if not match:
            raise AnswerKeyError(
                f"Formato de emparejamiento inválido: '{piece}'. "
                "Usá a->c, b->f, c->d"
            )
        left, right = match.group(1).lower(), _normalize_token(match.group(2))
        pairs[left] = right

    if not pairs:
        raise AnswerKeyError("La pregunta de emparejamiento no tiene pares.")

    return pairs


def parse_answer_line(raw_line: str, fallback_order: int) -> tuple[int, dict[str, Any]]:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        raise AnswerKeyError("Línea vacía.")

    match = LINE_PATTERN.match(line)
    if not match:
        raise AnswerKeyError(f"No se pudo interpretar la línea: {line}")

    order = int(match.group(1)) if match.group(1) else fallback_order
    body = match.group(2).strip()

    upper_body = body.upper()
    if "->" in body:
        pairs = parse_matching_pairs(body)
        options = [{"left": key, "right": ""} for key in pairs]
        return order, {
            "order": order,
            "type": "MATCHING",
            "prompt": None,
            "options": options,
            "correct_answer": pairs,
            "points": 1,
        }

    # Prefijos explícitos opcionales
    if upper_body.startswith("MATCH ") or upper_body.startswith("EMP "):
        body = body.split(" ", 1)[1].strip()
        pairs = parse_matching_pairs(body)
        options = [{"left": key, "right": ""} for key in pairs]
        return order, {
            "order": order,
            "type": "MATCHING",
            "prompt": None,
            "options": options,
            "correct_answer": pairs,
            "points": 1,
        }

    if upper_body.startswith("VF ") or upper_body.startswith("V/F "):
        token = _normalize_token(body.split(" ", 1)[1])
        if token not in {"V", "F"}:
            raise AnswerKeyError(f"Verdadero/Falso inválido en pregunta {order}: {body}")
        return order, {
            "order": order,
            "type": "TRUE_FALSE",
            "prompt": None,
            "options": ["V", "F"],
            "correct_answer": token,
            "points": 1,
        }

    token = _normalize_token(body)
    if token in {"V", "F"}:
        return order, {
            "order": order,
            "type": "TRUE_FALSE",
            "prompt": None,
            "options": ["V", "F"],
            "correct_answer": token,
            "points": 1,
        }

    if token in DEFAULT_MC:
        return order, {
            "order": order,
            "type": "MULTIPLE_CHOICE",
            "prompt": None,
            "options": DEFAULT_MC,
            "correct_answer": token,
            "points": 1,
        }

    raise AnswerKeyError(
        f"Pregunta {order}: '{body}' no es válida. "
        "Usá A–E, V/F, o emparejamiento a->c, b->f."
    )


def parse_answer_key(text: str, expected_count: int) -> list[dict[str, Any]]:
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]

    if not lines:
        raise AnswerKeyError("La clave de respuestas está vacía.")

    parsed: dict[int, dict[str, Any]] = {}
    sequential_index = 1

    for line in lines:
        while sequential_index in parsed:
            sequential_index += 1

        order, question = parse_answer_line(line, sequential_index)
        if order in parsed:
            raise AnswerKeyError(f"La pregunta {order} está repetida en la clave.")
        parsed[order] = question

        if order >= sequential_index:
            sequential_index = order + 1

    if expected_count <= 0:
        raise AnswerKeyError("La cantidad de preguntas debe ser mayor a cero.")

    missing = [number for number in range(1, expected_count + 1) if number not in parsed]
    if missing:
        preview = ", ".join(map(str, missing[:10]))
        suffix = "..." if len(missing) > 10 else ""
        raise AnswerKeyError(
            f"Faltan respuestas para {len(missing)} preguntas: {preview}{suffix}"
        )

    extra = [number for number in parsed if number > expected_count]
    if extra:
        raise AnswerKeyError(
            f"Hay respuestas fuera de rango (> {expected_count}): {', '.join(map(str, extra))}"
        )

    return [parsed[number] for number in range(1, expected_count + 1)]
