"""Utilidades compartidas."""

from __future__ import annotations

import secrets
import string
from datetime import datetime


ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_session_code(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def generate_id() -> str:
    return secrets.token_hex(12)


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def format_score(score: float) -> str:
    text = f"{score:.2f}"
    return text[:-3] if text.endswith(".00") else text


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
