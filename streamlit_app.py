"""EvaluAR - Examen en papel. Corrección digital."""

from __future__ import annotations

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
from evaluar.utils import format_datetime, format_score, is_session_open, question_type_label

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
                f"{exam.get('course') or 'Sin materia'} · "
                f"Nota máxima {exam['max_score']} · {exam['session_count']} sesiones"
            )
            if st.button("Administrar", key=f"exam_{exam['id']}"):
                st.session_state.exam_id = exam["id"]
                st.session_state.page = "exam_detail"
                st.rerun()


def page_new_exam() -> None:
    if not st.session_state.teacher:
        st.session_state.page = "auth"
        st.rerun()
        return

    st.subheader("Nuevo examen")
    title = st.text_input("Título", placeholder="Parcial 2 - Fisiopatología")
    course = st.text_input("Materia / Cátedra", placeholder="Medicina - 2° año")
    description = st.text_area("Instrucciones para el aula (opcional)")
    col1, col2, col3 = st.columns(3)
    with col1:
        max_score = st.number_input("Nota máxima", min_value=1.0, value=10.0, step=0.5)
    with col2:
        question_count = st.number_input("Cantidad de preguntas", min_value=1, max_value=200, value=50)
    with col3:
        show_detail = st.checkbox("Mostrar preguntas falladas al alumno", value=True)

    opt1, opt2 = st.columns(2)
    with opt1:
        default_mc_options = st.selectbox(
            "Opciones en opción múltiple (por defecto)",
            [3, 4, 5, 6],
            index=2,
        )
    with opt2:
        default_match_options = st.selectbox(
            "Opciones destino en emparejamiento (por defecto)",
            [3, 4, 5, 6],
            index=3,
        )

    st.markdown("### Clave de respuestas (tipos mixtos)")
    with st.expander("Ver sintaxis y ejemplos", expanded=True):
        st.markdown(
            """
            **Una línea por pregunta.** El sufijo **`/N`** indica cuántas opciones tiene
            esa pregunta (**3 a 6**). Si lo omitís, se usan los valores por defecto de arriba.

            | Tipo | Formato | Ejemplo |
            |------|---------|---------|
            | Opción múltiple (4 opc.) | letra + `/N` | `1/4: B` |
            | Opción múltiple (6 opc.) | letra + `/N` | `8/6: F` |
            | Verdadero / Falso | V o F (sin `/N`) | `2: V` |
            | Emparejamiento (6 destinos) | pares con flecha | `15/6: a->c, b->f, c->d` |

            Las líneas que empiezan con `#` se ignoran.
            """
        )
        st.code(
            "\n".join(
                [
                    "# Parcial mixto - 50 preguntas",
                    "1/5: B",
                    "2: V",
                    "3/4: C",
                    "4/5: A",
                    "5/6: F",
                    "# ... preguntas 6 a 14 ...",
                    "15/6: a->c, b->f, c->d",
                    "16/5: D",
                    "17: V",
                    "# ... completar hasta la pregunta 50 ...",
                ]
            ),
            language="text",
        )

    tpl1, tpl2 = st.columns([2, 1])
    with tpl1:
        matching_for_template = st.text_input(
            "Preguntas de emparejamiento para la plantilla (opcional)",
            placeholder="Ej. 15, 28, 42",
        )
    with tpl2:
        st.write("")
        st.write("")
        if st.button("Generar plantilla", use_container_width=True):
            from evaluar.answer_parser import generate_template

            matching_numbers: list[int] = []
            if matching_for_template.strip():
                matching_numbers = [
                    int(piece.strip())
                    for piece in matching_for_template.split(",")
                    if piece.strip()
                ]
            st.session_state.answer_key_draft = generate_template(
                int(question_count),
                int(default_mc_options),
                int(default_match_options),
                matching_numbers,
            )
            st.rerun()

    answers_text = st.text_area(
        "Respuestas correctas",
        height=280,
        key="answer_key_draft",
        placeholder="1/5: B\n2: V\n...\n15/6: a->c, b->f, c->d\n...",
        help=f"Debés definir las {int(question_count)} preguntas.",
    )

    if answers_text.strip():
        try:
            from evaluar.answer_parser import parse_answer_key

            preview = parse_answer_key(
                answers_text,
                int(question_count),
                int(default_mc_options),
                int(default_match_options),
            )
            st.markdown("**Vista previa detectada**")
            preview_rows = [
                {
                    "#": q["order"],
                    "Tipo": question_type_label(q["type"]),
                    "Opciones": len(q["options"]["targets"])
                    if q["type"] == "MATCHING" and isinstance(q["options"], dict)
                    else len(q["options"]),
                    "Correcta": q["correct_answer"],
                }
                for q in preview[:15]
            ]
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
            if len(preview) > 15:
                st.caption(f"Mostrando 15 de {len(preview)} preguntas.")
        except Exception as exc:
            st.warning(f"Revisá la clave: {exc}")

    if st.button("Crear examen", type="primary"):
        if not title.strip():
            st.error("El título es obligatorio.")
            return

        try:
            from evaluar.answer_parser import AnswerKeyError, parse_answer_key

            questions = parse_answer_key(
                answers_text,
                int(question_count),
                int(default_mc_options),
                int(default_match_options),
            )
            exam_id = create_exam(
                st.session_state.teacher["id"],
                title,
                course,
                description,
                float(max_score),
                show_detail,
                questions,
            )
            st.session_state.exam_id = exam_id
            st.session_state.page = "exam_detail"
            st.success("Examen creado.")
            st.rerun()
        except AnswerKeyError as exc:
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
        f"{exam.get('course') or 'Sin materia'} · {len(exam['questions'])} preguntas · "
        f"Nota máxima {exam['max_score']}"
    )
    if exam.get("description"):
        st.info(exam["description"])

    st.markdown("### Nueva sesión de aula")
    label = st.text_input("Etiqueta de sesión", placeholder="Comisión A - 05/07/2026")
    if st.button("Generar link de sesión", type="primary"):
        session = create_session(exam["id"], label)
        st.success(f"Sesión creada. Código: **{session['code']}**")
        st.code(f"?code={session['code']}", language="text")

    st.markdown("### Sesiones")
    if not exam["sessions"]:
        st.info("Todavía no hay sesiones.")
    for session in exam["sessions"]:
        with st.expander(f"{session.get('label') or 'Sesión'} · {session['code']}"):
            st.write(f"Envíos: {session['submission_count']}")
            st.code(f"?code={session['code']}", language="text")
            if st.button("Ver resultados", key=f"results_{session['id']}"):
                st.session_state.session_id = session["id"]
                st.session_state.page = "session_results"
                st.rerun()

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

    if st.button("← Volver"):
        st.session_state.page = "exam_detail"
        st.rerun()

    session = data["session"]
    exam = data["exam"]
    submissions = data["submissions"]

    st.subheader(f"Resultados · {exam['title']}")
    st.caption(f"Sesión {session['code']} · {session.get('label') or ''}")

    avg = 0 if not submissions else sum(s["score"] for s in submissions) / len(submissions)
    c1, c2, c3 = st.columns(3)
    c1.metric("Alumnos", len(submissions))
    c2.metric("Promedio", format_score(avg))
    c3.metric("Estado", "Abierta" if session["is_active"] else "Cerrada")

    if submissions:
        df = pd.DataFrame(
            [
                {
                    "Alumno": s["student_name"],
                    "DNI": s["student_dni"],
                    "Nota": s["score"],
                    "Aciertos": s["correct_count"],
                    "Errores": s["wrong_count"],
                    "Preguntas falladas": ", ".join(map(str, s["wrong_questions"])) or "—",
                    "Enviado": format_datetime(s["submitted_at"]),
                }
                for s in submissions
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"evaluar-{session['code']}.csv",
            mime="text/csv",
        )
    else:
        st.info("Todavía no hay respuestas enviadas.")

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
    st.caption(f"{exam.get('course') or ''} · {session.get('label') or ''}")

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
