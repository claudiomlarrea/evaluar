"""Capa de acceso a datos (SQLite local o PostgreSQL en producción)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from evaluar.db_backend import first_value, get_connection, row_to_dict, using_postgres
from evaluar.grading import grade_submission
from evaluar.utils import generate_id, generate_session_code, is_session_open, utc_now


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


SCHEMA_SQL = """
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
    career TEXT,
    subject TEXT,
    career_year TEXT,
    description TEXT,
    exam_date TEXT,
    exam_time TEXT,
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


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_exams(conn)


def _migrate_exams(conn: Any) -> None:
    columns = ("career", "subject", "career_year", "exam_date", "exam_time")
    if using_postgres():
        for column in columns:
            conn.execute(f"ALTER TABLE exams ADD COLUMN IF NOT EXISTS {column} TEXT")
        return

    existing = {row[1] for row in conn.execute("PRAGMA table_info(exams)")}
    for column in columns:
        if column not in existing:
            conn.execute(f"ALTER TABLE exams ADD COLUMN {column} TEXT")


def clear_all_exam_data() -> dict[str, int]:
    """Elimina exámenes, preguntas, códigos y respuestas. Conserva cuentas docentes."""
    with get_connection() as conn:
        counts = {
            "submissions": int(first_value(conn.execute("SELECT COUNT(*) FROM submissions").fetchone())),
            "sessions": int(first_value(conn.execute("SELECT COUNT(*) FROM sessions").fetchone())),
            "questions": int(first_value(conn.execute("SELECT COUNT(*) FROM questions").fetchone())),
            "exams": int(first_value(conn.execute("SELECT COUNT(*) FROM exams").fetchone())),
        }
        conn.executescript(
            """
            DELETE FROM submissions;
            DELETE FROM sessions;
            DELETE FROM questions;
            DELETE FROM exams;
            """
        )
    return counts


def count_teachers() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()
    return int(first_value(row))


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
    teacher = row_to_dict(row) or {}
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
    return [row_to_dict(row) or {} for row in rows]


def _insert_questions(conn: Any, exam_id: str, questions: list[dict[str, Any]]) -> None:
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


def _course_label(
    career: str | None,
    subject: str | None,
    career_year: str | None,
) -> str | None:
    return (
        " · ".join(
            piece
            for piece in [
                career.strip() if career else None,
                subject.strip() if subject else None,
                f"Año {career_year.strip()}" if career_year and career_year.strip() else None,
            ]
            if piece
        )
        or None
    )


def create_exam(
    teacher_id: str,
    title: str,
    career: str | None,
    subject: str | None,
    career_year: str | None,
    description: str | None,
    exam_date: str | None,
    exam_time: str | None,
    max_score: float,
    show_detail_to_student: bool,
    questions: list[dict[str, Any]],
) -> str:
    exam_id = generate_id()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO exams (
                id, teacher_id, title, course, career, subject, career_year,
                description, exam_date, exam_time, max_score, show_detail_to_student, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id,
                teacher_id,
                title.strip(),
                _course_label(career, subject, career_year),
                career.strip() if career else None,
                subject.strip() if subject else None,
                career_year.strip() if career_year else None,
                description.strip() if description else None,
                exam_date,
                exam_time,
                max_score,
                1 if show_detail_to_student else 0,
                utc_now(),
            ),
        )
        _insert_questions(conn, exam_id, questions)
    return exam_id


def update_exam(
    exam_id: str,
    teacher_id: str,
    title: str,
    career: str | None,
    subject: str | None,
    career_year: str | None,
    description: str | None,
    exam_date: str | None,
    exam_time: str | None,
    max_score: float,
    show_detail_to_student: bool,
    questions: list[dict[str, Any]],
) -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM exams WHERE id = ? AND teacher_id = ?",
            (exam_id, teacher_id),
        ).fetchone()
        if not row:
            raise ValueError("Examen no encontrado.")

        conn.execute(
            """
            UPDATE exams
            SET title = ?, course = ?, career = ?, subject = ?, career_year = ?,
                description = ?, exam_date = ?, exam_time = ?, max_score = ?,
                show_detail_to_student = ?
            WHERE id = ? AND teacher_id = ?
            """,
            (
                title.strip(),
                _course_label(career, subject, career_year),
                career.strip() if career else None,
                subject.strip() if subject else None,
                career_year.strip() if career_year else None,
                description.strip() if description else None,
                exam_date,
                exam_time,
                max_score,
                1 if show_detail_to_student else 0,
                exam_id,
                teacher_id,
            ),
        )
        conn.execute('DELETE FROM questions WHERE exam_id = ?', (exam_id,))
        _insert_questions(conn, exam_id, questions)


def duplicate_exam(exam_id: str, teacher_id: str) -> str:
    exam = get_exam(exam_id, teacher_id)
    if not exam:
        raise ValueError("Examen no encontrado.")

    questions: list[dict[str, Any]] = []
    for question in exam["questions"]:
        options = question.get("options")
        if isinstance(options, str):
            options = json.loads(options)
        correct = question.get("correct_answer")
        if question["type"] == "MATCHING" and isinstance(correct, str):
            correct = json.loads(correct)
        questions.append(
            {
                "order": question["order"],
                "type": question["type"],
                "prompt": question.get("prompt"),
                "options": options,
                "correct_answer": correct,
                "points": question.get("points", 1),
            }
        )

    return create_exam(
        teacher_id,
        f"{exam['title']} (copia)",
        exam.get("career"),
        exam.get("subject"),
        exam.get("career_year"),
        exam.get("description"),
        exam.get("exam_date"),
        exam.get("exam_time"),
        float(exam["max_score"]),
        bool(exam["show_detail_to_student"]),
        questions,
    )


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

    result = row_to_dict(exam) or {}
    result["questions"] = [row_to_dict(q) or {} for q in questions]
    result["sessions"] = [row_to_dict(s) or {} for s in sessions]
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


def set_session_active(session_id: str, teacher_id: str, active: bool) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT s.id FROM sessions s
            JOIN exams e ON e.id = s.exam_id
            WHERE s.id = ? AND e.teacher_id = ?
            """,
            (session_id, teacher_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE sessions
            SET is_active = ?, closes_at = ?
            WHERE id = ?
            """,
            (1 if active else 0, None if active else utc_now(), session_id),
        )
    return True


def get_session_by_code(code: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        if not session:
            return None
        session_dict = row_to_dict(session) or {}
        exam = conn.execute(
            "SELECT * FROM exams WHERE id = ?",
            (session_dict["exam_id"],),
        ).fetchone()
        questions = conn.execute(
            'SELECT * FROM questions WHERE exam_id = ? ORDER BY "order" ASC',
            (session_dict["exam_id"],),
        ).fetchall()

    return {
        "session": session_dict,
        "exam": row_to_dict(exam) or {},
        "questions": [row_to_dict(q) or {} for q in questions],
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


def _load_json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _load_json_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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

        session_dict = row_to_dict(session) or {}
        exam = conn.execute("SELECT * FROM exams WHERE id = ?", (session_dict["exam_id"],)).fetchone()
        questions = conn.execute(
            'SELECT * FROM questions WHERE exam_id = ? ORDER BY "order" ASC',
            (session_dict["exam_id"],),
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
        item = row_to_dict(row) or {}
        item["wrong_questions"] = _load_json_list(item.get("wrong_questions"))
        item["answers"] = _load_json_dict(item.get("answers"))
        parsed_submissions.append(item)

    question_stats = []
    for question in questions:
        q = row_to_dict(question) or {}
        order = q["order"]
        correct = incorrect = unanswered = 0
        for submission in parsed_submissions:
            answer = submission["answers"].get(str(order), "").strip()
            wrong_list = submission["wrong_questions"]
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
                "type": q["type"],
                "correct": correct,
                "incorrect": incorrect,
                "unanswered": unanswered,
                "success_rate": 0 if total == 0 else round((correct / total) * 100),
            }
        )

    return {
        "session": session_dict,
        "exam": row_to_dict(exam) or {},
        "questions": [row_to_dict(q) or {} for q in questions],
        "submissions": parsed_submissions,
        "question_stats": question_stats,
    }
