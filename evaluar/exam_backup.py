"""Exportar e importar exámenes como respaldo local (.json)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

BACKUP_KIND = "exam"
BACKUP_VERSION = 1


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize_question(question: dict[str, Any]) -> dict[str, Any]:
    options = _parse_json_field(question.get("options"))
    correct = _parse_json_field(question.get("correct_answer"))
    return {
        "order": int(question["order"]),
        "type": question["type"],
        "prompt": question.get("prompt"),
        "options": options if options is not None else [],
        "correct_answer": correct,
        "points": float(question.get("points") or 1),
    }


def build_exam_backup(exam: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluar_backup": BACKUP_KIND,
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exam": {
            "title": exam["title"],
            "career": exam.get("career"),
            "subject": exam.get("subject"),
            "career_year": exam.get("career_year"),
            "description": exam.get("description"),
            "exam_date": exam.get("exam_date"),
            "exam_time": exam.get("exam_time"),
            "max_score": float(exam["max_score"]),
            "pass_min_score": (
                float(exam["pass_min_score"])
                if exam.get("pass_min_score") is not None
                else None
            ),
            "show_detail_to_student": bool(exam.get("show_detail_to_student")),
            "scoring_mode": exam.get("scoring_mode") or "equal",
            "questions": [_normalize_question(q) for q in exam.get("questions", [])],
        },
    }


def exam_backup_bytes(exam: dict[str, Any]) -> bytes:
    return json.dumps(build_exam_backup(exam), ensure_ascii=False, indent=2).encode("utf-8")


def exam_backup_filename(exam: dict[str, Any]) -> str:
    title = str(exam.get("title") or "examen").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-") or "examen"
    return f"evaluar-examen-{slug}.json"


def parse_exam_backup(raw: bytes | str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("El archivo no es un JSON válido.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Formato de respaldo inválido.")
    if payload.get("evaluar_backup") != BACKUP_KIND:
        raise ValueError("Este archivo no es un respaldo de examen de EvaluAR.")
    if int(payload.get("version", 0)) != BACKUP_VERSION:
        raise ValueError("Versión de respaldo no compatible.")

    exam = payload.get("exam")
    if not isinstance(exam, dict):
        raise ValueError("El respaldo no contiene datos del examen.")

    title = str(exam.get("title") or "").strip()
    if not title:
        raise ValueError("El examen del respaldo no tiene título.")

    questions_raw = exam.get("questions")
    if not isinstance(questions_raw, list) or not questions_raw:
        raise ValueError("El respaldo no tiene preguntas.")

    scoring_mode = exam.get("scoring_mode") or "equal"
    if scoring_mode not in {"equal", "manual"}:
        raise ValueError("Modo de puntaje inválido en el respaldo.")

    questions = [_normalize_question(q) for q in questions_raw]

    return {
        "title": title,
        "career": exam.get("career"),
        "subject": exam.get("subject"),
        "career_year": exam.get("career_year"),
        "description": exam.get("description"),
        "exam_date": exam.get("exam_date"),
        "exam_time": exam.get("exam_time"),
        "max_score": float(exam.get("max_score") or 10),
        "pass_min_score": (
            float(exam["pass_min_score"])
            if exam.get("pass_min_score") is not None
            else None
        ),
        "show_detail_to_student": bool(exam.get("show_detail_to_student", True)),
        "scoring_mode": scoring_mode,
        "questions": questions,
    }
