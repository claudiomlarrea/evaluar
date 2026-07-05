"""EvaluAR - Examen en papel. Corrección digital."""

from __future__ import annotations

import io
import json

import pandas as pd
import streamlit as st

from evaluar.database import (
    create_exam,
    create_session,
    get_exam,
    get_session_by_code,
    get_session_results,
    init_db,
    list_exams,
    login_teacher,
    register_teacher,
    submit_answers,
)
from evaluar.answer_parser import letters_for_count
from evaluar.question_builder import TYPE_CHOICES, build_all_questions, default_question_draft
from evaluar.utils import format_datetime, format_score, is_session_open, question_type_label

QUESTIONS_PER_PAGE = 5

st.set_page_config(
    page_title="EvaluAR",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

DEFAULT_MC = ["A", "B", "C", "D", "E", "F"]


def _load_question_options(raw: str, qtype: str) -> tuple[list[str], list[dict[str, str]]]:
    """Devuelve (opciones MC o targets, ítems de emparejamiento)."""
    parsed = json.loads(raw)
    if qtype == "MATCHING":
        if isinstance(parsed, dict):
            return parsed.get("targets", DEFAULT_MC), parsed.get("items", [])
        if isinstance(parsed, list):
            return DEFAULT_MC, parsed
        return DEFAULT_MC, []
    if isinstance(parsed, list):
        return parsed, []
    return DEFAULT_MC, []


def _submissions_dataframe(submissions: list[dict], max_score: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Apellido y nombre": s["student_name"],
                "DNI / Matrícula": s["student_dni"],
                "Nota": s["score"],
                "Aciertos": s["correct_count"],
                "Errores": s["wrong_count"],
                "Sin responder": s["unanswered_count"],
                "Preguntas falladas": ", ".join(map(str, s["wrong_questions"])) or "—",
                "Fecha de envío": format_datetime(s["submitted_at"]),
            }
            for s in submissions
        ]
    )


def _export_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Notas")
    return buffer.getvalue()


def ensure_state() -> None:
    defaults = {
        "teacher": None,
        "page": "home",
        "exam_id": None,
        "session_id": None,
        "student_code": None,
        "student_step": "identify",
        "student_result": None,
        "answer_key_draft": "",
        "exam_wizard_step": "general",
        "exam_wizard_general": {},
        "exam_wizard_drafts": [],
        "exam_wizard_page": 1,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_header() -> None:
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
          <div style="background:#0d9488;color:white;width:42px;height:42px;border-radius:12px;
                      display:flex;align-items:center;justify-content:center;font-weight:700;">E</div>
          <div>
            <div style="font-size:1.4rem;font-weight:700;">EvaluAR</div>
            <div style="color:#64748b;font-size:0.9rem;">Examen en papel. Corrección digital.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    st.sidebar.title("Navegación")
    if st.session_state.teacher:
        st.sidebar.success(f"Docente: {st.session_state.teacher['name']}")
        if st.sidebar.button("Panel docente", use_container_width=True):
            st.session_state.page = "panel"
            st.rerun()
        if st.sidebar.button("Nuevo examen", use_container_width=True):
            st.session_state.page = "new_exam"
            st.rerun()
        if st.sidebar.button("Cerrar sesión", use_container_width=True):
            st.session_state.teacher = None
            st.session_state.page = "home"
            st.rerun()
    else:
        if st.sidebar.button("Acceso docente", use_container_width=True):
            st.session_state.page = "auth"
            st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("**Link alumno**")
    code = st.sidebar.text_input("Código de sesión", placeholder="Ej. ABC12345")
    if st.sidebar.button("Ir a carga de respuestas", use_container_width=True) and code.strip():
        st.session_state.student_code = code.strip().upper()
        st.session_state.page = "student"
        st.session_state.student_step = "identify"
        st.session_state.student_result = None
        st.rerun()


def page_home() -> None:
    st.title("Evaluación presencial híbrida")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            Los alumnos rinden en **papel**. Después cargan sus respuestas desde el celular.
            El docente sube la clave de respuestas y el sistema corrige al instante.
            """
        )
        if st.button("Soy docente", type="primary"):
            st.session_state.page = "auth"
            st.rerun()
    with col2:
        st.info(
            "Pensado para carreras con alto volumen: 100 alumnos, 50 preguntas, "
            "opción múltiple, V/F y emparejamiento."
        )


def page_auth() -> None:
    st.subheader("Acceso docente")
    tab_login, tab_register = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with tab_login:
        name = st.text_input("Nombre completo", key="login_name")
        pin = st.text_input("PIN", type="password", key="login_pin")
        if st.button("Ingresar", type="primary"):
            teacher = login_teacher(name, pin)
            if not teacher:
                st.error("Credenciales incorrectas.")
            else:
                st.session_state.teacher = teacher
                st.session_state.page = "panel"
                st.success("Sesión iniciada.")
                st.rerun()

    with tab_register:
        name = st.text_input("Nombre completo", key="register_name")
        pin = st.text_input("PIN (mínimo 4 caracteres)", type="password", key="register_pin")
        if st.button("Crear cuenta", type="primary"):
            if len(pin.strip()) < 4:
                st.error("El PIN debe tener al menos 4 caracteres.")
            else:
                try:
                    teacher = register_teacher(name, pin)
                    st.session_state.teacher = teacher
                    st.session_state.page = "panel"
                    st.success("Cuenta creada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar: {exc}")


def page_panel() -> None:
    if not st.session_state.teacher:
        st.session_state.page = "auth"
        st.rerun()
        return

    st.subheader("Panel docente")
    if st.button("➕ Nuevo examen"):
        st.session_state.page = "new_exam"
        st.rerun()

    exams = list_exams(st.session_state.teacher["id"])
    if not exams:
        st.info("Todavía no hay exámenes. Creá el primero con la clave de respuestas.")
        return

    for exam in exams:
        with st.expander(f"{exam['title']} · {exam['question_count']} preguntas"):
            st.caption(
                f"{exam.get('career') or exam.get('course') or 'Sin carrera'} · "
                f"{exam.get('subject') or ''} · "
                f"{('Año ' + exam['career_year']) if exam.get('career_year') else ''} · "
                f"Nota máxima {exam['max_score']} · {exam['session_count']} sesiones"
            )
            if st.button("Administrar", key=f"exam_{exam['id']}"):
                st.session_state.exam_id = exam["id"]
                st.session_state.page = "exam_detail"
                st.rerun()


def _render_question_editor(question_number: int) -> None:
    type_label = st.radio(
        "Tipo de pregunta",
        list(TYPE_CHOICES.keys()),
        horizontal=True,
        key=f"q{question_number}_type_label",
    )
    qtype = TYPE_CHOICES[type_label]

    if qtype == "MULTIPLE_CHOICE":
        option_count = st.selectbox(
            "Cantidad de opciones (distractores)",
            [3, 4, 5, 6],
            index=2,
            key=f"q{question_number}_option_count",
        )
        options = letters_for_count(int(option_count))
        st.selectbox(
            "Respuesta correcta",
            options,
            key=f"q{question_number}_mc_answer",
        )

    elif qtype == "TRUE_FALSE":
        st.radio(
            "Respuesta correcta",
            ["V", "F"],
            format_func=lambda value: "Verdadero" if value == "V" else "Falso",
            horizontal=True,
            key=f"q{question_number}_vf_answer",
        )

    else:
        col1, col2 = st.columns(2)
        with col1:
            target_count = st.selectbox(
                "Cantidad de opciones destino",
                [3, 4, 5, 6],
                index=3,
                key=f"q{question_number}_target_count",
            )
        with col2:
            item_count = st.selectbox(
                "Cantidad de ítems a emparejar",
                [3, 4, 5, 6],
                index=0,
                key=f"q{question_number}_item_count",
            )

        targets = letters_for_count(int(target_count))
        labels = [chr(ord("a") + index) for index in range(int(item_count))]
        st.caption("Indicá con qué opción se empareja cada ítem.")
        for label in labels:
            st.selectbox(
                f"Ítem {label} →",
                targets,
                key=f"q{question_number}_match_{label}",
            )


def _collect_question_draft(question_number: int) -> dict:
    type_label = st.session_state.get(f"q{question_number}_type_label", "Opción múltiple")
    qtype = TYPE_CHOICES[type_label]
    draft = {"order": question_number, "type": qtype}

    if qtype == "MULTIPLE_CHOICE":
        draft["option_count"] = int(
            st.session_state.get(f"q{question_number}_option_count", 5)
        )
        draft["mc_answer"] = st.session_state.get(f"q{question_number}_mc_answer", "A")
    elif qtype == "TRUE_FALSE":
        draft["vf_answer"] = st.session_state.get(f"q{question_number}_vf_answer", "V")
    else:
        item_count = int(st.session_state.get(f"q{question_number}_item_count", 3))
        draft["target_count"] = int(
            st.session_state.get(f"q{question_number}_target_count", 6)
        )
        draft["item_count"] = item_count
        labels = [chr(ord("a") + index) for index in range(item_count)]
        draft["matching_answers"] = {
            label: st.session_state.get(f"q{question_number}_match_{label}", "A")
            for label in labels
        }

    return draft


def _init_question_widgets(question_count: int) -> None:
    for number in range(1, question_count + 1):
        if f"q{number}_type_label" not in st.session_state:
            defaults = default_question_draft(number)
            st.session_state[f"q{number}_type_label"] = "Opción múltiple"
            st.session_state[f"q{number}_option_count"] = defaults["option_count"]
            st.session_state[f"q{number}_mc_answer"] = defaults["mc_answer"]
            st.session_state[f"q{number}_vf_answer"] = defaults["vf_answer"]
            st.session_state[f"q{number}_target_count"] = defaults["target_count"]
            st.session_state[f"q{number}_item_count"] = defaults["item_count"]
            for label in defaults["matching_items"]:
                st.session_state[f"q{number}_match_{label}"] = defaults["matching_answers"][label]


def page_new_exam() -> None:
    if not st.session_state.teacher:
        st.session_state.page = "auth"
        st.rerun()
        return

    st.subheader("Nuevo examen")
    step = st.session_state.exam_wizard_step

    if step == "general":
        st.markdown("### 1. Datos de la carrera y del examen")

        col1, col2, col3 = st.columns(3)
        with col1:
            career = st.text_input("Carrera *", placeholder="Medicina")
        with col2:
            subject = st.text_input("Asignatura *", placeholder="Fisiopatología")
        with col3:
            career_year = st.text_input("Año de la carrera *", placeholder="2°")

        title = st.text_input(
            "Nombre del examen *",
            placeholder="Parcial 2",
            help="Ej. Parcial 1, Final, Recuperatorio",
        )
        description = st.text_area("Instrucciones para el aula (opcional)")

        col4, col5, col6 = st.columns(3)
        with col4:
            question_count = st.number_input(
                "Cantidad total de preguntas *",
                min_value=1,
                max_value=200,
                value=50,
            )
        with col5:
            max_score = st.number_input("Nota máxima", min_value=1.0, value=10.0, step=0.5)
        with col6:
            show_detail = st.checkbox("Mostrar preguntas falladas al alumno", value=True)

        st.info(
            "En el siguiente paso configurarás **cada pregunta**: tipo, cantidad de opciones "
            "(si corresponde) y respuesta correcta."
        )

        nav1, nav2 = st.columns([1, 1])
        with nav1:
            if st.button("← Volver al panel"):
                st.session_state.page = "panel"
                st.rerun()
        with nav2:
            if st.button("Continuar → Clave de respuestas", type="primary"):
                if not career.strip() or not subject.strip() or not career_year.strip():
                    st.error("Completá carrera, asignatura y año.")
                elif not title.strip():
                    st.error("Completá el nombre del examen.")
                else:
                    st.session_state.exam_wizard_general = {
                        "career": career.strip(),
                        "subject": subject.strip(),
                        "career_year": career_year.strip(),
                        "title": title.strip(),
                        "description": description.strip(),
                        "question_count": int(question_count),
                        "max_score": float(max_score),
                        "show_detail": show_detail,
                    }
                    _init_question_widgets(int(question_count))
                    st.session_state.exam_wizard_step = "questions"
                    st.session_state.exam_wizard_page = 1
                    st.rerun()

    else:
        general = st.session_state.exam_wizard_general
        if not general:
            st.session_state.exam_wizard_step = "general"
            st.rerun()
            return

        question_count = int(general["question_count"])
        total_pages = max(1, (question_count + QUESTIONS_PER_PAGE - 1) // QUESTIONS_PER_PAGE)
        current_page = int(st.session_state.exam_wizard_page)
        current_page = max(1, min(current_page, total_pages))

        st.markdown("### 2. Clave de respuestas — pregunta por pregunta")
        st.caption(
            f"{general['career']} · {general['subject']} · Año {general['career_year']} · "
            f"{general['title']} · {question_count} preguntas"
        )

        start = (current_page - 1) * QUESTIONS_PER_PAGE + 1
        end = min(question_count, start + QUESTIONS_PER_PAGE - 1)
        st.progress(min(current_page / total_pages, 1.0))
        st.write(f"Configurando preguntas **{start}** a **{end}** de **{question_count}**")

        for number in range(start, end + 1):
            with st.expander(f"Pregunta {number}", expanded=True):
                _render_question_editor(number)

        nav1, nav2, nav3, nav4 = st.columns(4)
        with nav1:
            if st.button("← Datos generales"):
                st.session_state.exam_wizard_step = "general"
                st.rerun()
        with nav2:
            if current_page > 1 and st.button("← Página anterior"):
                st.session_state.exam_wizard_page = current_page - 1
                st.rerun()
        with nav3:
            if current_page < total_pages and st.button("Página siguiente →"):
                st.session_state.exam_wizard_page = current_page + 1
                st.rerun()
        with nav4:
            if st.button("Crear examen", type="primary"):
                try:
                    drafts = [_collect_question_draft(number) for number in range(1, question_count + 1)]
                    questions = build_all_questions(drafts)
                    exam_id = create_exam(
                        st.session_state.teacher["id"],
                        general["title"],
                        general["career"],
                        general["subject"],
                        general["career_year"],
                        general.get("description") or None,
                        general["max_score"],
                        general["show_detail"],
                        questions,
                    )
                    st.session_state.exam_id = exam_id
                    st.session_state.exam_wizard_step = "general"
                    st.session_state.exam_wizard_general = {}
                    st.session_state.exam_wizard_page = 1
                    st.session_state.page = "exam_detail"
                    st.success("Examen creado.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"No se pudo crear el examen: {exc}")



def page_exam_detail() -> None:
    if not st.session_state.teacher or not st.session_state.exam_id:
        st.session_state.page = "panel"
        st.rerun()
        return

    exam = get_exam(st.session_state.exam_id, st.session_state.teacher["id"])
    if not exam:
        st.error("Examen no encontrado.")
        return

    if st.button("← Volver al panel"):
        st.session_state.page = "panel"
        st.rerun()

    st.subheader(exam["title"])
    st.caption(
        f"{exam.get('career') or ''} · {exam.get('subject') or ''} · "
        f"{('Año ' + exam['career_year']) if exam.get('career_year') else ''} · "
        f"{len(exam['questions'])} preguntas · Nota máxima {exam['max_score']}"
    )
    if exam.get("description"):
        st.info(exam["description"])

    st.markdown("### Nueva sesión de aula")
    label = st.text_input("Etiqueta de sesión", placeholder="Comisión A - 05/07/2026")
    if st.button("Generar link de sesión", type="primary"):
        session = create_session(exam["id"], label)
        st.success(f"Sesión creada. Código: **{session['code']}**")
        st.code(f"?code={session['code']}", language="text")

    st.markdown("### Sesiones del parcial")
    if not exam["sessions"]:
        st.info("Generá una sesión arriba para obtener el link que usarán los alumnos.")
    for session in exam["sessions"]:
        header = f"{session.get('label') or 'Sesión'} · código **{session['code']}**"
        st.markdown(header)
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            st.write(f"**{session['submission_count']}** alumnos enviaron respuestas")
        with col2:
            st.code(f"?code={session['code']}", language="text")
        with col3:
            if st.button(
                "Ver planilla de alumnos",
                key=f"results_{session['id']}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.session_id = session["id"]
                st.session_state.page = "session_results"
                st.rerun()
        st.divider()

    st.markdown("### Clave de respuestas")
    rows = [
        {
            "#": q["order"],
            "Tipo": question_type_label(q["type"]),
            "Referencia": q.get("prompt") or "—",
            "Correcta": q["correct_answer"],
            "Pts": q["points"],
        }
        for q in exam["questions"]
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def page_session_results() -> None:
    if not st.session_state.teacher or not st.session_state.session_id:
        st.session_state.page = "panel"
        st.rerun()
        return

    data = get_session_results(st.session_state.session_id, st.session_state.teacher["id"])
    if not data:
        st.error("Sesión no encontrada.")
        return

    if st.button("← Volver al examen"):
        st.session_state.page = "exam_detail"
        st.rerun()

    session = data["session"]
    exam = data["exam"]
    submissions = data["submissions"]

    st.subheader("Planilla de alumnos")
    st.caption(
        f"{exam.get('career') or ''} · {exam.get('subject') or ''} · "
        f"{exam['title']} · Sesión {session['code']}"
    )

    avg = 0 if not submissions else sum(s["score"] for s in submissions) / len(submissions)
    c1, c2, c3 = st.columns(3)
    c1.metric("Alumnos evaluados", len(submissions))
    c2.metric("Promedio", format_score(avg))
    c3.metric("Nota máxima", exam["max_score"])

    if submissions:
        df = _submissions_dataframe(submissions, float(exam["max_score"]))
        st.dataframe(df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Descargar Excel (.xlsx)",
                data=_export_excel(df),
                file_name=f"evaluar-{session['code']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "Descargar CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"evaluar-{session['code']}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        st.info(
            "Todavía no hay respuestas. Compartí el link con los alumnos después del parcial "
            f"en papel: `?code={session['code']}`"
        )

    st.markdown("### Estadísticas por pregunta")
    st.dataframe(pd.DataFrame(data["question_stats"]), use_container_width=True, hide_index=True)


def page_student() -> None:
    code = st.session_state.student_code or st.query_params.get("code", "")
    if not code:
        st.warning("Ingresá un código de sesión desde la barra lateral.")
        return

    payload = get_session_by_code(code)
    if not payload:
        st.error("Sesión no encontrada.")
        return

    session = payload["session"]
    exam = payload["exam"]
    questions = payload["questions"]

    st.subheader(exam["title"])
    parts = [
        exam.get("career"),
        exam.get("subject"),
        f"Año {exam['career_year']}" if exam.get("career_year") else None,
        session.get("label"),
    ]
    st.caption(" · ".join(part for part in parts if part))

    if not is_session_open(session):
        st.error("Esta sesión no está abierta para envíos.")
        return

    if st.session_state.student_result:
        result = st.session_state.student_result
        st.success("Respuestas enviadas correctamente.")
        st.metric("Tu nota", f"{format_score(result['score'])} / {result['max_score']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Aciertos", result["correct_count"])
        c2.metric("Errores", result["wrong_count"])
        c3.metric("Sin responder", result["unanswered_count"])
        if result["show_detail"] and result["wrong_questions"]:
            st.warning("Preguntas incorrectas u omitidas: " + ", ".join(map(str, result["wrong_questions"])))
        return

    if st.session_state.student_step == "identify":
        name = st.text_input("Apellido y nombre", placeholder="García, Ana")
        dni = st.text_input("DNI o matrícula", placeholder="45123456")
        if st.button("Continuar", type="primary"):
            if not name.strip() or not dni.strip():
                st.error("Completá nombre y DNI.")
            else:
                st.session_state.student_name = name.strip()
                st.session_state.student_dni = dni.strip()
                st.session_state.student_step = "answers"
                st.rerun()
        return

    st.markdown("Marcá la opción que elegiste en tu cuadernillo de papel.")
    answers: dict[str, str] = {}
    page_size = 10
    total_pages = max(1, (len(questions) + page_size - 1) // page_size)
    page_num = st.number_input("Página", min_value=1, max_value=total_pages, value=1)
    start_idx = (page_num - 1) * page_size
    visible = questions[start_idx : start_idx + page_size]

    for question in visible:
        order = question["order"]
        st.markdown(f"**Pregunta {order}**")
        if question.get("prompt"):
            st.caption(question["prompt"])
        qtype = question["type"]
        if qtype == "MULTIPLE_CHOICE":
            mc_options, _ = _load_question_options(question["options"], qtype)
            choice = st.radio("Opción", mc_options, key=f"ans_{order}", horizontal=True)
            answers[str(order)] = choice
        elif qtype == "TRUE_FALSE":
            choice = st.radio(
                "Respuesta",
                ["V", "F"],
                format_func=lambda x: "Verdadero" if x == "V" else "Falso",
                key=f"ans_{order}",
                horizontal=True,
            )
            answers[str(order)] = choice
        else:
            targets, pairs = _load_question_options(question["options"], qtype)
            matching: dict[str, str] = {}
            for pair in pairs:
                left_key = str(pair["left"]).lower()
                letter = st.selectbox(
                    f"Ítem **{pair['left']}** →",
                    ["", *targets],
                    key=f"ans_{order}_{left_key}",
                )
                if letter:
                    matching[left_key] = letter
            answers[str(order)] = json.dumps(matching)

    if page_num == total_pages and st.button("Enviar respuestas", type="primary"):
        try:
            result = submit_answers(
                code,
                st.session_state.student_name,
                st.session_state.student_dni,
                answers,
            )
            st.session_state.student_result = result
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"No se pudieron enviar las respuestas: {exc}")


def main() -> None:
    ensure_state()

    code_param = st.query_params.get("code")
    if code_param:
        st.session_state.student_code = code_param.upper()
        st.session_state.page = "student"

    render_header()
    render_sidebar()

    page = st.session_state.page
    if page == "home":
        page_home()
    elif page == "auth":
        page_auth()
    elif page == "panel":
        page_panel()
    elif page == "new_exam":
        page_new_exam()
    elif page == "exam_detail":
        page_exam_detail()
    elif page == "session_results":
        page_session_results()
    elif page == "student":
        page_student()
    else:
        page_home()


if __name__ == "__main__":
    main()
