"""Parser de clave de respuestas con tipos mixtos y 3–6 opciones."""

from __future__ import annotations

import re
from typing import Any

MIN_OPTIONS = 3
MAX_OPTIONS = 6
ALL_LETTERS = list("ABCDEFGHIJ")

LINE_PATTERN = re.compile(
    r"^\s*(?:(\d+)(?:/([3-6]))?\s*(?:[:.)-]\s*|\s+))?(.+?)\s*$"
)
PAIR_PATTERN = re.compile(r"^\s*([a-zA-Z0-9]+)\s*(?:->|:|=)\s*([a-zA-Z0-9]+)\s*$")


class AnswerKeyError(ValueError):
    """Error al interpretar la clave de respuestas."""


def letters_for_count(count: int) -> list[str]:
    if count < MIN_OPTIONS or count > MAX_OPTIONS:
        raise AnswerKeyError(
            f"La cantidad de opciones debe estar entre {MIN_OPTIONS} y {MAX_OPTIONS}."
        )
    return ALL_LETTERS[:count]


def _normalize_token(value: str) -> str:
    return value.strip().upper()


def parse_matching_pairs(raw: str, target_letters: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    valid_targets = {_normalize_token(letter) for letter in target_letters}

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
        if right not in valid_targets:
            raise AnswerKeyError(
                f"La respuesta '{right}' no está entre las opciones disponibles "
                f"({', '.join(target_letters)})."
            )
        pairs[left] = right

    if not pairs:
        raise AnswerKeyError("La pregunta de emparejamiento no tiene pares.")

    return pairs


def generate_template(
    question_count: int,
    default_mc_options: int = 5,
    default_match_options: int = 6,
    matching_questions: list[int] | None = None,
) -> str:
    matching_set = set(matching_questions or [])
    lines = [
        "# Plantilla EvaluAR — completá cada línea",
        "# /N = cantidad de opciones destino (3 a 6)",
        "# MC: letra | V/F: V o F | Emparejamiento: a->c, b->f, c->d",
        "",
    ]

    for number in range(1, question_count + 1):
        if number in matching_set:
            lines.append(
                f"{number}/{default_match_options}: a->, b->, c->"
            )
        else:
            lines.append(f"{number}/{default_mc_options}: ")

    return "\n".join(lines)


def parse_answer_line(
    raw_line: str,
    fallback_order: int,
    default_mc_options: int,
    default_match_options: int,
) -> tuple[int, dict[str, Any]]:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        raise AnswerKeyError("Línea vacía.")

    match = LINE_PATTERN.match(line)
    if not match:
        raise AnswerKeyError(f"No se pudo interpretar la línea: {line}")

    order = int(match.group(1)) if match.group(1) else fallback_order
    option_count = int(match.group(2)) if match.group(2) else None
    body = match.group(3).strip()
    upper_body = body.upper()

    if "->" in body:
        count = option_count or default_match_options
        targets = letters_for_count(count)
        pairs = parse_matching_pairs(body, targets)
        return order, {
            "order": order,
            "type": "MATCHING",
            "prompt": None,
            "options": {
                "items": [{"left": key, "right": ""} for key in pairs],
                "targets": targets,
            },
            "correct_answer": pairs,
            "points": 1,
        }

    if upper_body.startswith("MATCH ") or upper_body.startswith("EMP "):
        body = body.split(" ", 1)[1].strip()
        count = option_count or default_match_options
        targets = letters_for_count(count)
        pairs = parse_matching_pairs(body, targets)
        return order, {
            "order": order,
            "type": "MATCHING",
            "prompt": None,
            "options": {
                "items": [{"left": key, "right": ""} for key in pairs],
                "targets": targets,
            },
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

    count = option_count or default_mc_options
    mc_options = letters_for_count(count)
    if token in mc_options:
        return order, {
            "order": order,
            "type": "MULTIPLE_CHOICE",
            "prompt": None,
            "options": mc_options,
            "correct_answer": token,
            "points": 1,
        }

    raise AnswerKeyError(
        f"Pregunta {order}: '{body}' no es válida para {count} opciones "
        f"({', '.join(mc_options)}), V/F, o emparejamiento a->c."
    )


def parse_answer_key(
    text: str,
    expected_count: int,
    default_mc_options: int = 5,
    default_match_options: int = 6,
) -> list[dict[str, Any]]:
    letters_for_count(default_mc_options)
    letters_for_count(default_match_options)

    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        raise AnswerKeyError("La clave de respuestas está vacía.")

    parsed: dict[int, dict[str, Any]] = {}
    sequential_index = 1

    for line in lines:
        while sequential_index in parsed:
            sequential_index += 1

        order, question = parse_answer_line(
            line,
            sequential_index,
            default_mc_options,
            default_match_options,
        )
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
