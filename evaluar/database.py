"""Capa de acceso a SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from evaluar.grading import grade_submission
from evaluar.utils import generate_id, generate_session_code, is_session_open

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluar.db"


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def utc_now() -> str:
    return datetime.utcnow().isoformat()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teachers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                pin_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exams (
                id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                title TEXT NOT NULL,
                course TEXT,
                description TEXT,
                max_score REAL NOT NULL DEFAULT 10,
                show_detail_to_student INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                exam_id TEXT NOT NULL,
                "order" INTEGER NOT NULL,
                type TEXT NOT NULL,
                prompt TEXT,
                options TEXT NOT NULL DEFAULT '[]',
                correct_answer TEXT NOT NULL,
                points REAL NOT NULL DEFAULT 1,
                UNIQUE(exam_id, "order"),
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                exam_id TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                label TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                opens_at TEXT,
                closes_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                student_dni TEXT NOT NULL,
                answers TEXT NOT NULL,
                score REAL NOT NULL,
                correct_count INTEGER NOT NULL,
                wrong_count INTEGER NOT NULL,
                unanswered_count INTEGER NOT NULL,
                wrong_questions TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                UNIQUE(session_id, student_dni),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            """
        )


def register_teacher(name: str, pin: str) -> dict[str, Any]:
    teacher_id = generate_id()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teachers (id, name, pin_hash, created_at) VALUES (?, ?, ?, ?)",
            (teacher_id, name.strip(), hash_pin(pin), utc_now()),
        )
    return {"id": teacher_id, "name": name.strip()}


def login_teacher(name: str, pin: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM teachers WHERE name = ?",
            (name.strip(),),
        ).fetchone()
    if not row:
        return None
    teacher = dict(row)
    if teacher["pin_hash"] != hash_pin(pin):
        return None
    return {"id": teacher["id"], "name": teacher["name"]}


def list_exams(teacher_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.*,
                   (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.id) AS question_count,
                   (SELECT COUNT(*) FROM sessions s WHERE s.exam_id = e.id) AS session_count
            FROM exams e
            WHERE e.teacher_id = ?
            ORDER BY e.created_at DESC
            """,
            (teacher_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_exam(
    teacher_id: str,
    title: str,
    course: str | None,
    description: str | None,
    max_score: float,
    show_detail_to_student: bool,
    questions: list[dict[str, Any]],
) -> str:
    exam_id = generate_id()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO exams (id, teacher_id, title, course, description, max_score,
                               show_detail_to_student, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id,
                teacher_id,
                title.strip(),
                course.strip() if course else None,
                description.strip() if description else None,
                max_score,
                1 if show_detail_to_student else 0,
                utc_now(),
            ),
        )
        for question in questions:
            correct = question["correct_answer"]
            if isinstance(correct, dict):
                correct = json.dumps(correct)
            conn.execute(
                """
                INSERT INTO questions (id, exam_id, "order", type, prompt, options,
                                       correct_answer, points)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id(),
                    exam_id,
                    question["order"],
                    question["type"],
                    question.get("prompt"),
                    json.dumps(question.get("options", [])),
                    correct,
                    question.get("points", 1),
                ),
            )
    return exam_id


def get_exam(exam_id: str, teacher_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM exams WHERE id = ?"
    params: tuple[Any, ...] = (exam_id,)
    if teacher_id:
        query += " AND teacher_id = ?"
        params = (exam_id, teacher_id)

    with get_connection() as conn:
        exam = conn.execute(query, params).fetchone()
        if not exam:
            return None
        questions = conn.execute(
            'SELECT * FROM questions WHERE exam_id = ? ORDER BY "order" ASC',
            (exam_id,),
        ).fetchall()
        sessions = conn.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM submissions sub WHERE sub.session_id = s.id) AS submission_count
            FROM sessions s
            WHERE s.exam_id = ?
            ORDER BY s.created_at DESC
            """,
            (exam_id,),
        ).fetchall()

    result = dict(exam)
    result["questions"] = [dict(q) for q in questions]
    result["sessions"] = [dict(s) for s in sessions]
    return result


def create_session(exam_id: str, label: str | None = None) -> dict[str, Any]:
    session_id = generate_id()
    code = generate_session_code()
    with get_connection() as conn:
        while conn.execute("SELECT 1 FROM sessions WHERE code = ?", (code,)).fetchone():
            code = generate_session_code()
        conn.execute(
            """
            INSERT INTO sessions (id, exam_id, code, label, is_active, opens_at, closes_at, created_at)
            VALUES (?, ?, ?, ?, 1, NULL, NULL, ?)
            """,
            (session_id, exam_id, code, label.strip() if label else None, utc_now()),
        )
    return {"id": session_id, "code": code, "label": label}


def get_session_by_code(code: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        if not session:
            return None
        exam = conn.execute(
            "SELECT * FROM exams WHERE id = ?",
            (session["exam_id"],),
        ).fetchone()
        questions = conn.execute(
            'SELECT * FROM questions WHERE exam_id = ? ORDER BY "order" ASC',
            (session["exam_id"],),
        ).fetchall()

    return {
        "session": dict(session),
        "exam": dict(exam),
        "questions": [dict(q) for q in questions],
    }


def submit_answers(
    code: str,
    student_name: str,
    student_dni: str,
    answers: dict[str, str],
) -> dict[str, Any]:
    payload = get_session_by_code(code)
    if not payload:
        raise ValueError("Sesión no encontrada.")

    session = payload["session"]
    exam = payload["exam"]
    questions = payload["questions"]

    if not is_session_open(session):
        raise ValueError("Esta sesión no está abierta para envíos.")

    dni = "".join(ch for ch in student_dni if ch.isdigit())
    if not dni:
        raise ValueError("DNI o matrícula inválido.")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM submissions WHERE session_id = ? AND student_dni = ?",
            (session["id"], dni),
        ).fetchone()
        if existing:
            raise ValueError("Ya enviaste tus respuestas para este parcial.")

    result = grade_submission(questions, answers, float(exam["max_score"]))
    submission_id = generate_id()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO submissions (
                id, session_id, student_name, student_dni, answers, score,
                correct_count, wrong_count, unanswered_count, wrong_questions, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                session["id"],
                student_name.strip(),
                dni,
                json.dumps(answers),
                result["score"],
                result["correct_count"],
                result["wrong_count"],
                result["unanswered_count"],
                json.dumps(result["wrong_questions"]),
                utc_now(),
            ),
        )

    return {
        "id": submission_id,
        **result,
        "total_questions": len(questions),
        "show_detail": bool(exam["show_detail_to_student"]),
        "max_score": float(exam["max_score"]),
    }


def get_session_results(session_id: str, teacher_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        session = conn.execute(
            """
            SELECT s.* FROM sessions s
            JOIN exams e ON e.id = s.exam_id
            WHERE s.id = ? AND e.teacher_id = ?
            """,
            (session_id, teacher_id),
        ).fetchone()
        if not session:
            return None

        exam = conn.execute("SELECT * FROM exams WHERE id = ?", (session["exam_id"],)).fetchone()
        questions = conn.execute(
            'SELECT * FROM questions WHERE exam_id = ? ORDER BY "order" ASC',
            (session["exam_id"],),
        ).fetchall()
        submissions = conn.execute(
            """
            SELECT * FROM submissions
            WHERE session_id = ?
            ORDER BY score DESC, student_name ASC
            """,
            (session_id,),
        ).fetchall()

    parsed_submissions = []
    for row in submissions:
        item = dict(row)
        item["wrong_questions"] = json.loads(item["wrong_questions"])
        parsed_submissions.append(item)

    question_stats = []
    for question in questions:
        order = question["order"]
        correct = incorrect = unanswered = 0
        for submission in parsed_submissions:
            answers = json.loads(submission["answers"])
            answer = answers.get(str(order), "").strip()
            wrong_list = json.loads(submission["wrong_questions"])
            if not answer:
                unanswered += 1
            elif order in wrong_list:
                incorrect += 1
            else:
                correct += 1
        total = len(submissions)
        question_stats.append(
            {
                "order": order,
                "type": question["type"],
                "correct": correct,
                "incorrect": incorrect,
                "unanswered": unanswered,
                "success_rate": 0 if total == 0 else round((correct / total) * 100),
            }
        )

    return {
        "session": dict(session),
        "exam": dict(exam),
        "questions": [dict(q) for q in questions],
        "submissions": parsed_submissions,
        "question_stats": question_stats,
    }
