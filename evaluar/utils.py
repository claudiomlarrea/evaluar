"""Utilidades compartidas."""

from __future__ import annotations

import secrets
from datetime import datetime


ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_session_code(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def generate_id() -> str:
    return secrets.token_hex(12)


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def format_score(score: float) -> str:
    """Formatea puntos o notas; sin decimales si el valor es entero."""
    rounded = round(float(score))
    if abs(float(score) - rounded) < 1e-9:
        return str(int(rounded))
    text = f"{score:.2f}"
    return text[:-3] if text.endswith(".00") else text


def round_grade(score: float) -> int:
    """Nota final del alumno, siempre entera."""
    return int(round(float(score)))


def format_grade(score: float) -> str:
    return str(round_grade(score))


def format_datetime(value: str | None) -> str:
    if not value:
        return "Sin límite"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def format_exam_schedule(exam_date: str | None, exam_time: str | None = None) -> str | None:
    if not exam_date:
        return None
    try:
        day = datetime.fromisoformat(exam_date).strftime("%d/%m/%Y")
    except ValueError:
        day = exam_date
    if exam_time:
        return f"{day} · {exam_time}"
    return day


def question_total_points(questions: list[dict]) -> float:
    return sum(float(q.get("points") or 1) for q in questions)


def format_grading_summary(
    earned_points: float,
    total_points: float,
    max_score: float,
    score: float | None = None,
) -> str:
    final = score if score is not None else (
        0.0 if total_points == 0 else round((earned_points / total_points) * max_score)
    )
    return (
        f"{format_score(earned_points)} / {format_score(total_points)} pts · "
        f"Nota {format_grade(final)} / {format_grade(max_score)}"
    )


def default_pass_min_score(max_score: float) -> float:
    return round(float(max_score) * 0.6, 2)


def passing_status(score: float, pass_min_score: float | None) -> str | None:
    if pass_min_score is None:
        return None
    return "Aprobado" if float(score) >= float(pass_min_score) else "Desaprobado"


def question_type_label(qtype: str) -> str:
    return {
        "MULTIPLE_CHOICE": "Opción múltiple",
        "TRUE_FALSE": "Verdadero / Falso",
        "MATCHING": "Emparejamiento",
    }.get(qtype, qtype)


def is_session_open(session: dict) -> bool:
    if not session.get("is_active"):
        return False
    now = datetime.utcnow()
    opens_at = session.get("opens_at")
    closes_at = session.get("closes_at")
    if opens_at:
        try:
            if now < datetime.fromisoformat(opens_at.replace("Z", "+00:00")).replace(tzinfo=None):
                return False
        except ValueError:
            pass
    if closes_at:
        try:
            if now > datetime.fromisoformat(closes_at.replace("Z", "+00:00")).replace(tzinfo=None):
                return False
        except ValueError:
            pass
    return True
