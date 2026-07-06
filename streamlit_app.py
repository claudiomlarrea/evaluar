"""EvaluAR - Examen en papel. Corrección digital."""

from __future__ import annotations

import io
import json
import base64
import html
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
import streamlit.components.v1 as components

from evaluar.database import (
    clear_all_exam_data,
    count_teachers,
    create_exam,
    create_session,
    duplicate_exam,
    get_exam,
    get_session_by_code,
    get_session_results,
    init_db,
    list_exams,
    login_teacher,
    register_teacher,
    set_session_active,
    submit_answers,
    update_exam,
)
from evaluar.db_backend import database_label
from evaluar.answer_parser import letters_for_count
from evaluar.question_builder import TYPE_CHOICES, TYPE_LABELS, build_all_questions, default_question_draft
from evaluar.utils import format_datetime, format_exam_schedule, format_score, is_session_open, question_type_label

QUESTIONS_PER_PAGE = 5
ROOT_DIR = Path(__file__).resolve().parent
LOGO_PATH = ROOT_DIR / "assets" / "logo-observatorio-ia.png"
OBSERVATORIO_NAME = "Observatorio de Inteligencia Artificial"
INSTITUTION_NAME = "Universidad Católica de Cuyo"
TEACHER_COUNT_BASELINE = 326

st.set_page_config(
    page_title="EvaluAR",
    page_icon=str(LOGO_PATH) if LOGO_PATH.is_file() else "📝",
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


def _student_query(code: str) -> str:
    return f"?code={code.upper()}"


def _app_base_url() -> str:
    """URL pública de la app (Streamlit Cloud)."""
    try:
        headers = st.context.headers
        host = headers.get("Host") or headers.get("host", "")
        if host:
            return f"https://{host.split(',')[0].strip().rstrip('/')}"
    except Exception:
        pass
    return ""


def _student_share_url(code: str) -> str:
    base_url = _app_base_url()
    if not base_url:
        return ""
    return f"{base_url}?code={code.upper()}"


def _qr_png_bytes(url: str) -> bytes:
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_session_share(code: str, key_prefix: str) -> None:
    """Botones para copiar código, URL, mensaje, QR y descargar QR."""
    code = code.upper()
    base_url = _app_base_url()
    share_url = _student_share_url(code)
    html_id = "".join(ch if ch.isalnum() else "_" for ch in key_prefix)

    if base_url:
        st.caption(f"URL EvaluAR: `{base_url}` · Código: **`{code}`**")
    else:
        st.caption(f"Código del parcial: **`{code}`** (copiá también la URL desde el navegador)")

    code_js = json.dumps(code)
    share_js = json.dumps(share_url)
    base_js = json.dumps(base_url)
    message_js = json.dumps(
        "Parcial en papel. Después cargá tus respuestas en EvaluAR:\n"
        + (f"{share_url or base_url}\n" if (share_url or base_url) else "")
        + f"Código del parcial: {code}\n"
        + "En la app elegí «Soy alumno» e ingresá el código."
    )

    btn_style = (
        "width:100%;box-sizing:border-box;padding:0.7rem 0.85rem;border-radius:0.5rem;"
        "cursor:pointer;font-size:0.9rem;font-weight:500;line-height:1.2;white-space:nowrap;"
    )
    btn_outline = (
        f"{btn_style}border:1px solid #cbd5e1;background:#fff;color:#0f172a;"
    )
    btn_primary = (
        f"{btn_style}border:1px solid #044A30;background:#044A30;color:#fff;font-weight:600;"
    )

    if share_url:
        qr_b64 = base64.b64encode(_qr_png_bytes(share_url)).decode("ascii")
        components.html(
            f"""
            <div style="display:flex;gap:1rem;align-items:flex-start;font-family:sans-serif;">
              <div style="text-align:center;flex-shrink:0;">
                <img id="qr-{html_id}" src="data:image/png;base64,{qr_b64}" width="130" height="130"
                     alt="QR EvaluAR" style="display:block;border:1px solid #e2e8f0;border-radius:0.5rem;" />
                <p style="margin:0.35rem 0 0;font-size:0.78rem;color:#64748b;">QR para el aula</p>
              </div>
              <div style="flex:1;display:flex;flex-direction:column;gap:0.55rem;min-width:180px;">
                <button type="button" id="copy-code-{html_id}" style="{btn_outline}">
                  Copiar código
                </button>
                <button type="button" id="copy-url-{html_id}" style="{btn_outline}">
                  Copiar URL de EvaluAR
                </button>
                <button type="button" id="copy-link-{html_id}" style="{btn_outline}">
                  Copiar link directo
                </button>
                <button type="button" id="copy-msg-{html_id}" style="{btn_primary}">
                  Copiar mensaje WhatsApp
                </button>
                <button type="button" id="copy-qr-{html_id}" style="{btn_outline}">
                  Copiar QR
                </button>
                <a id="download-qr-{html_id}" download="evaluar-{code}.png"
                   href="data:image/png;base64,{qr_b64}"
                   style="{btn_outline}display:block;text-align:center;text-decoration:none;">
                  Descargar QR (PNG)
                </a>
              </div>
            </div>
            <script>
            document.getElementById("copy-code-{html_id}").onclick = function() {{
                navigator.clipboard.writeText({code_js});
            }};
            document.getElementById("copy-url-{html_id}").onclick = function() {{
                const url = {base_js};
                if (url) navigator.clipboard.writeText(url);
                else alert("Copiá la URL desde la barra del navegador.");
            }};
            document.getElementById("copy-link-{html_id}").onclick = function() {{
                const url = {share_js};
                if (url) navigator.clipboard.writeText(url);
                else alert("No hay link directo disponible.");
            }};
            document.getElementById("copy-msg-{html_id}").onclick = function() {{
                navigator.clipboard.writeText({message_js});
            }};
            document.getElementById("copy-qr-{html_id}").onclick = async function() {{
                try {{
                    const response = await fetch(document.getElementById("qr-{html_id}").src);
                    const blob = await response.blob();
                    await navigator.clipboard.write([new ClipboardItem({{ "image/png": blob }})]);
                }} catch (error) {{
                    alert("No se pudo copiar el QR. Usá «Descargar QR (PNG)».");
                }}
            }};
            </script>
            """,
            height=300,
        )
    else:
        components.html(
            f"""
            <div style="display:flex;flex-direction:column;gap:0.55rem;width:100%;font-family:sans-serif;">
              <button type="button" id="copy-code-{html_id}" style="{btn_outline}">
                Copiar código
              </button>
              <button type="button" id="copy-msg-{html_id}" style="{btn_primary}">
                Copiar mensaje WhatsApp
              </button>
            </div>
            <script>
            document.getElementById("copy-code-{html_id}").onclick = function() {{
                navigator.clipboard.writeText({code_js});
            }};
            document.getElementById("copy-msg-{html_id}").onclick = function() {{
                navigator.clipboard.writeText({message_js});
            }};
            </script>
            """,
            height=120,
        )


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
        "last_created_session_code": None,
        "flash_session_code": None,
        "exam_wizard_mode": "create",
        "edit_exam_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _displayed_teacher_count() -> int:
    return TEACHER_COUNT_BASELINE + count_teachers()


def _logo_base64() -> str:
    if LOGO_PATH.is_file():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return ""


def render_header() -> None:
    obs = html.escape(OBSERVATORIO_NAME)
    inst = html.escape(INSTITUTION_NAME)
    b64 = _logo_base64()
    if b64:
        logo_html = (
            f'<img src="data:image/jpeg;base64,{b64}" alt="Logo {obs}" '
            'class="evaluar-logo" />'
        )
    else:
        logo_html = (
            '<div style="background:#044A30;color:white;width:56px;height:56px;'
            'border-radius:50%;display:flex;align-items:center;justify-content:center;'
            'font-weight:700;">E</div>'
        )

    st.markdown(
        f"""
        <style>
        .evaluar-logo {{
            display: block;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid #044A30;
            box-shadow: 0 2px 8px rgba(4, 74, 48, 0.15);
        }}
        </style>
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">
          {logo_html}
          <div>
            <div style="font-size:1.4rem;font-weight:700;color:#044A30;">EvaluAR</div>
            <div style="color:#64748b;font-size:0.9rem;">Examen en papel. Corrección digital.</div>
            <div style="color:#94a3b8;font-size:0.78rem;margin-top:2px;">{obs} · {inst}</div>
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
    st.sidebar.markdown("**Acceso alumno**")
    st.sidebar.caption("Ingresá el código del parcial o abrí el link del docente.")
    code = st.sidebar.text_input("Código del parcial", placeholder="Ej. JT7MH2GD", key="sidebar_student_code")
    if st.sidebar.button("Cargar mis respuestas", use_container_width=True) and code.strip():
        st.session_state.student_code = code.strip().upper()
        st.session_state.page = "student"
        st.session_state.student_step = "identify"
        st.session_state.student_result = None
        st.rerun()

    st.sidebar.divider()
    teacher_total = _displayed_teacher_count()
    label = "docente usa" if teacher_total == 1 else "docentes usan"
    st.sidebar.caption(f"**{teacher_total}** {label} EvaluAR")
    st.sidebar.caption(f"Base de datos: {database_label()}")


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

    st.divider()
    st.subheader("Soy alumno")
    st.markdown(
        "Después del parcial en papel, ingresá el **código** que te dio el docente "
        "(o abrí el link que te compartió)."
    )
    student_code = st.text_input(
        "Código del parcial",
        placeholder="Ej. JT7MH2GD",
        key="home_student_code",
    )
    if st.button("Ingresar y cargar mis respuestas", type="primary"):
        if not student_code.strip():
            st.error("Ingresá el código del parcial.")
        else:
            st.session_state.student_code = student_code.strip().upper()
            st.session_state.page = "student"
            st.session_state.student_step = "identify"
            st.session_state.student_result = None
            st.rerun()


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
    else:
        for exam in exams:
            schedule = format_exam_schedule(exam.get("exam_date"), exam.get("exam_time"))
            with st.expander(f"{exam['title']} · {exam['question_count']} preguntas"):
                st.caption(
                    f"{exam.get('career') or exam.get('course') or 'Sin carrera'} · "
                    f"{exam.get('subject') or ''} · "
                    f"{('Año ' + exam['career_year']) if exam.get('career_year') else ''} · "
                    f"{schedule + ' · ' if schedule else ''}"
                    f"Nota máxima {exam['max_score']} · {exam['session_count']} códigos"
                )
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("Administrar", key=f"exam_{exam['id']}", use_container_width=True):
                        st.session_state.exam_id = exam["id"]
                        st.session_state.page = "exam_detail"
                        st.rerun()
                with col_b:
                    if st.button("Editar", key=f"edit_{exam['id']}", use_container_width=True):
                        _begin_edit_exam(exam["id"], st.session_state.teacher["id"])
                        st.session_state.page = "new_exam"
                        st.rerun()
                with col_c:
                    if st.button("Duplicar", key=f"dup_{exam['id']}", use_container_width=True):
                        try:
                            new_id = duplicate_exam(exam["id"], st.session_state.teacher["id"])
                            st.session_state.exam_id = new_id
                            st.session_state.page = "exam_detail"
                            st.success("Examen duplicado.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"No se pudo duplicar: {exc}")

    with st.expander("Limpiar datos de prueba"):
        st.warning(
            "Elimina **todos** los exámenes, códigos del parcial y respuestas de alumnos. "
            "Las cuentas docentes se conservan."
        )
        confirm = st.text_input("Escribí BORRAR para confirmar", key="clear_exam_data_confirm")
        if st.button("Eliminar todos los exámenes y códigos"):
            if confirm.strip().upper() != "BORRAR":
                st.error("Escribí BORRAR para confirmar.")
            else:
                deleted = clear_all_exam_data()
                st.session_state.exam_id = None
                st.session_state.session_id = None
                st.session_state.flash_session_code = None
                st.success(
                    f"Listo: {deleted['exams']} exámenes, {deleted['sessions']} códigos "
                    f"y {deleted['submissions']} respuestas eliminados."
                )
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


def _init_question_widgets_from_exam(questions: list[dict]) -> None:
    for question in questions:
        number = int(question["order"])
        qtype = question["type"]
        st.session_state[f"q{number}_type_label"] = TYPE_LABELS.get(qtype, "Opción múltiple")

        options_raw = question.get("options")
        if isinstance(options_raw, str):
            options_raw = json.loads(options_raw)

        if qtype == "MULTIPLE_CHOICE":
            options = options_raw if isinstance(options_raw, list) else []
            st.session_state[f"q{number}_option_count"] = len(options) or 5
            st.session_state[f"q{number}_mc_answer"] = question["correct_answer"]
        elif qtype == "TRUE_FALSE":
            st.session_state[f"q{number}_vf_answer"] = question["correct_answer"]
        elif qtype == "MATCHING":
            targets = options_raw.get("targets", []) if isinstance(options_raw, dict) else []
            items = options_raw.get("items", []) if isinstance(options_raw, dict) else []
            st.session_state[f"q{number}_target_count"] = len(targets) or 6
            st.session_state[f"q{number}_item_count"] = len(items) or 3
            correct = question.get("correct_answer")
            if isinstance(correct, str):
                correct = json.loads(correct)
            for label in [item["left"] for item in items]:
                st.session_state[f"q{number}_match_{label}"] = (correct or {}).get(label, "A")


def _begin_edit_exam(exam_id: str, teacher_id: str) -> None:
    exam = get_exam(exam_id, teacher_id)
    if not exam:
        return
    st.session_state.exam_wizard_mode = "edit"
    st.session_state.edit_exam_id = exam_id
    st.session_state.exam_wizard_general = {
        "career": exam.get("career") or "",
        "subject": exam.get("subject") or "",
        "career_year": exam.get("career_year") or "",
        "title": exam["title"],
        "description": exam.get("description") or "",
        "exam_date": exam.get("exam_date") or date.today().isoformat(),
        "exam_time": exam.get("exam_time") or "09:00",
        "question_count": len(exam["questions"]),
        "max_score": float(exam["max_score"]),
        "show_detail": bool(exam["show_detail_to_student"]),
    }
    _init_question_widgets_from_exam(exam["questions"])
    st.session_state.exam_wizard_step = "general"
    st.session_state.exam_wizard_page = 1


def _reset_exam_wizard() -> None:
    st.session_state.exam_wizard_step = "general"
    st.session_state.exam_wizard_general = {}
    st.session_state.exam_wizard_page = 1
    st.session_state.exam_wizard_mode = "create"
    st.session_state.edit_exam_id = None


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

    editing = st.session_state.exam_wizard_mode == "edit"
    st.subheader("Editar examen" if editing else "Nuevo examen")
    step = st.session_state.exam_wizard_step
    preset = st.session_state.exam_wizard_general

    if step == "general":
        st.markdown("### 1. Datos de la carrera y del examen")

        col1, col2, col3 = st.columns(3)
        with col1:
            career = st.text_input("Carrera *", placeholder="Medicina", value=preset.get("career", ""))
        with col2:
            subject = st.text_input("Asignatura *", placeholder="Fisiopatología", value=preset.get("subject", ""))
        with col3:
            career_year = st.text_input("Año de la carrera *", placeholder="2°", value=preset.get("career_year", ""))

        title = st.text_input(
            "Nombre del examen *",
            placeholder="Parcial 2",
            value=preset.get("title", ""),
            help="Ej. Parcial 1, Final, Recuperatorio",
        )

        preset_date = date.today()
        if preset.get("exam_date"):
            try:
                preset_date = date.fromisoformat(preset["exam_date"])
            except ValueError:
                pass
        preset_time = time(9, 0)
        if preset.get("exam_time"):
            try:
                hour, minute = preset["exam_time"].split(":")
                preset_time = time(int(hour), int(minute))
            except ValueError:
                pass

        col_date, col_time = st.columns(2)
        with col_date:
            exam_date = st.date_input(
                "Fecha del parcial *",
                value=preset_date,
                format="DD/MM/YYYY",
                help="Elegí día, mes y año desde el calendario.",
            )
        with col_time:
            exam_time = st.time_input(
                "Hora del parcial",
                value=preset_time,
                step=timedelta(minutes=5),
                help="Podés ajustar la hora manualmente.",
            )

        description = st.text_area(
            "Instrucciones para el aula (opcional)",
            value=preset.get("description", ""),
        )

        col4, col5, col6 = st.columns(3)
        with col4:
            question_count = st.number_input(
                "Cantidad total de preguntas *",
                min_value=1,
                max_value=200,
                value=int(preset.get("question_count", 50)),
            )
        with col5:
            max_score = st.number_input(
                "Nota máxima",
                min_value=1.0,
                value=float(preset.get("max_score", 10.0)),
                step=0.5,
            )
        with col6:
            show_detail = st.checkbox(
                "Mostrar preguntas falladas al alumno",
                value=bool(preset.get("show_detail", True)),
            )

        st.info(
            "En el siguiente paso configurarás **cada pregunta**: tipo, cantidad de opciones "
            "(si corresponde) y respuesta correcta."
        )

        nav1, nav2 = st.columns([1, 1])
        with nav1:
            if st.button("← Volver"):
                _reset_exam_wizard()
                st.session_state.page = "exam_detail" if editing else "panel"
                st.rerun()
        with nav2:
            if st.button("Continuar → Clave de respuestas", type="primary"):
                if not career.strip() or not subject.strip() or not career_year.strip():
                    st.error("Completá carrera, asignatura y año.")
                elif not title.strip():
                    st.error("Completá el nombre del examen.")
                else:
                    previous_count = int(preset.get("question_count", 0))
                    st.session_state.exam_wizard_general = {
                        "career": career.strip(),
                        "subject": subject.strip(),
                        "career_year": career_year.strip(),
                        "title": title.strip(),
                        "description": description.strip(),
                        "exam_date": exam_date.isoformat(),
                        "exam_time": exam_time.strftime("%H:%M"),
                        "question_count": int(question_count),
                        "max_score": float(max_score),
                        "show_detail": show_detail,
                    }
                    if int(question_count) != previous_count:
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
            f"{general['title']} · "
            f"{format_exam_schedule(general.get('exam_date'), general.get('exam_time')) or 'Sin fecha'} · "
            f"{question_count} preguntas"
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
            save_label = "Guardar cambios" if editing else "Crear examen"
            if st.button(save_label, type="primary"):
                try:
                    drafts = [_collect_question_draft(number) for number in range(1, question_count + 1)]
                    questions = build_all_questions(drafts)
                    if editing:
                        update_exam(
                            st.session_state.edit_exam_id,
                            st.session_state.teacher["id"],
                            general["title"],
                            general["career"],
                            general["subject"],
                            general["career_year"],
                            general.get("description") or None,
                            general.get("exam_date"),
                            general.get("exam_time"),
                            general["max_score"],
                            general["show_detail"],
                            questions,
                        )
                        st.session_state.exam_id = st.session_state.edit_exam_id
                        success_msg = "Examen actualizado."
                    else:
                        exam_id = create_exam(
                            st.session_state.teacher["id"],
                            general["title"],
                            general["career"],
                            general["subject"],
                            general["career_year"],
                            general.get("description") or None,
                            general.get("exam_date"),
                            general.get("exam_time"),
                            general["max_score"],
                            general["show_detail"],
                            questions,
                        )
                        st.session_state.exam_id = exam_id
                        success_msg = "Examen creado."
                    _reset_exam_wizard()
                    st.session_state.page = "exam_detail"
                    st.success(success_msg)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"No se pudo guardar el examen: {exc}")



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

    action1, action2 = st.columns(2)
    with action1:
        if st.button("Editar examen y clave de respuestas", use_container_width=True):
            _begin_edit_exam(exam["id"], st.session_state.teacher["id"])
            st.session_state.page = "new_exam"
            st.rerun()
    with action2:
        if st.button("Duplicar examen", use_container_width=True):
            try:
                new_id = duplicate_exam(exam["id"], st.session_state.teacher["id"])
                st.session_state.exam_id = new_id
                st.success("Examen duplicado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo duplicar: {exc}")

    st.subheader(exam["title"])
    schedule = format_exam_schedule(exam.get("exam_date"), exam.get("exam_time"))
    st.caption(
        f"{exam.get('career') or ''} · {exam.get('subject') or ''} · "
        f"{('Año ' + exam['career_year']) if exam.get('career_year') else ''} · "
        f"{schedule + ' · ' if schedule else ''}"
        f"{len(exam['questions'])} preguntas · Nota máxima {exam['max_score']}"
    )
    if exam.get("description"):
        st.info(exam["description"])

    with st.expander("¿Cómo funciona el día del parcial?", expanded=False):
        st.markdown(
            """
            **Antes del parcial:** ya cargaste el examen y la clave de respuestas (al crear el examen).

            **El día del parcial:**
            1. Generá el **código del parcial** (botón de abajo) — **una sola vez** por comisión.
            2. Enviá a los alumnos la **URL de EvaluAR** + el **código** (WhatsApp).
            3. Rinden en **papel** en el aula; recogen los cuadernillos.
            4. Los alumnos entran a EvaluAR → **Soy alumno** → cargan sus respuestas con el código.
            5. Vos ves acá la **planilla de notas** y descargás Excel.
            6. Cuando la comisión terminó de cargar, **cerrá el código** (sección «Control de acceso»).

            El código **no es** para rendir online: es para **cargar respuestas después** del parcial en papel.
            """
        )

    st.markdown("### Código del parcial para alumnos")
    st.info(
        "**Generar código** crea el identificador (ej. HG3QK5DR) que los alumnos usarán "
        "**después** de rendir en papel para marcar sus respuestas en el celular."
    )

    col_label, col_btn = st.columns([3, 1])
    with col_label:
        label = st.text_input(
            "Nombre de la comisión (opcional)",
            placeholder="Ej. Comisión A - turno mañana",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button("Generar código", type="primary", use_container_width=True):
            session = create_session(exam["id"], label)
            st.session_state.flash_session_code = session["code"]
            st.rerun()

    sessions = exam["sessions"]
    if not sessions:
        st.warning(
            "Todavía no hay código. Hacé clic en **Generar código** arriba. "
            "Después vas a poder compartirlo y **cerrarlo** cuando la comisión termine de cargar respuestas."
        )
    else:
        if len(sessions) > 1:
            st.warning(
                f"Hay **{len(sessions)} códigos** generados. Usá **uno solo** por parcial. "
                "Elegí el correcto abajo."
            )

        options = [
            f"{s['code']} · {(s.get('label') or 'Sin etiqueta')} · "
            f"{s['submission_count']} alumnos · "
            f"{'abierto' if is_session_open(s) else 'cerrado'}"
            for s in sessions
        ]
        default_index = 0
        flash = st.session_state.get("flash_session_code")
        if flash:
            for index, session in enumerate(sessions):
                if session["code"] == flash:
                    default_index = index
                    break
        default_index = min(default_index, max(0, len(sessions) - 1))

        selected_index = st.selectbox(
            "Código activo de este parcial",
            range(len(sessions)),
            format_func=lambda i: options[i],
            index=default_index,
            key="active_session_code_select",
        )
        active = sessions[selected_index]
        session_open = is_session_open(active)

        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Código para alumnos", active["code"])
        metric2.metric("Respuestas cargadas", active["submission_count"])
        metric3.metric("Estado del código", "Abierto" if session_open else "Cerrado")
        metric4.metric("Nota máxima", exam["max_score"])

        st.markdown("#### Control de acceso de alumnos")
        if session_open:
            st.warning(
                "El código **está abierto**: los alumnos pueden seguir cargando respuestas. "
                "Cuando la comisión terminó (o pasó el plazo), cerralo acá abajo."
            )
            if st.button(
                "Cerrar código — no más respuestas de alumnos",
                type="primary",
                use_container_width=True,
                key="close_session_btn",
            ):
                set_session_active(active["id"], st.session_state.teacher["id"], False)
                st.success("Código cerrado. Los alumnos ya no pueden enviar respuestas.")
                st.rerun()
        else:
            st.success(
                "Código **cerrado**. Los alumnos ya no pueden cargar respuestas nuevas. "
                "Vos seguís viendo la planilla y descargando Excel."
            )
            if st.button(
                "Reabrir código para permitir más cargas",
                use_container_width=True,
                key="reopen_session_btn",
            ):
                set_session_active(active["id"], st.session_state.teacher["id"], True)
                st.success("Código reabierto.")
                st.rerun()

        st.divider()

        if st.button("Ver planilla de notas y descargar Excel", type="primary"):
            st.session_state.session_id = active["id"]
            st.session_state.page = "session_results"
            st.rerun()

        st.markdown("**Enviar a la comisión (después de rendir en papel)**")
        _render_session_share(active["code"], "active_session")

        if len(sessions) > 1:
            with st.expander("Ver todos los códigos generados"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Código": s["code"],
                                "Etiqueta": s.get("label") or "—",
                                "Envíos": s["submission_count"],
                            }
                            for s in sessions
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    with st.expander("Clave de respuestas cargada"):
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
    raw_code = st.session_state.student_code or st.query_params.get("code", "")
    if isinstance(raw_code, list):
        raw_code = raw_code[0] if raw_code else ""
    code = str(raw_code or "").strip().upper()
    if not code:
        st.warning("Ingresá un código del parcial desde la barra lateral.")
        return

    payload = get_session_by_code(code)
    if not payload:
        st.error("Código no encontrado. Verificá que sea el correcto.")
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
        if isinstance(code_param, list):
            code_param = code_param[0] if code_param else ""
        if code_param:
            st.session_state.student_code = str(code_param).upper()
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
