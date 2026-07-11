"""EvaluAR - Examen en papel. Corrección digital."""

from __future__ import annotations

import io
import json
import base64
import html
import time as time_module
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
import streamlit.components.v1 as components

from evaluar.database import (
    clear_all_exam_data,
    get_usage_count,
    increment_usage_count,
    create_exam,
    create_session,
    duplicate_exam,
    delete_exam,
    delete_session,
    ensure_migrations,
    get_exam,
    get_session_by_code,
    get_session_results,
    init_schema,
    list_exams,
    login_teacher,
    register_teacher,
    set_session_active,
    submit_answers,
    update_exam,
)
from evaluar.answer_parser import letters_for_count
from evaluar.exam_backup import exam_backup_bytes, exam_backup_filename, parse_exam_backup
from evaluar.question_builder import (
    TYPE_CHOICES,
    TYPE_LABELS,
    build_all_questions,
    default_question_draft,
    drafts_from_exam_questions,
    item_labels,
)
from evaluar.utils import (
    format_datetime,
    format_exam_schedule,
    format_grading_summary,
    format_grade,
    format_score,
    default_pass_min_score,
    is_session_open,
    passing_status,
    question_total_points,
    question_type_label,
)

QUESTIONS_PER_PAGE = 10
# Incrementar cuando se agreguen migraciones en database.py
MIGRATION_VERSION = 1
ROOT_DIR = Path(__file__).resolve().parent
LOGO_PATH = ROOT_DIR / "assets" / "logo-observatorio-ia.png"
OBSERVATORIO_NAME = "Observatorio de Inteligencia Artificial"
INSTITUTION_NAME = "Universidad Católica de Cuyo"
BG_MAIN = "#D5E9E2"
BG_SIDEBAR = "#C6E0D6"
BG_SURFACE = "#FFFFFF"
BRAND_GREEN = "#044A30"
BORDER_SOFT = "#B8D4C8"
st.set_page_config(
    page_title="EvaluAR",
    page_icon=str(LOGO_PATH) if LOGO_PATH.is_file() else "📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _bootstrap_database(_migration_version: int) -> bool:
    """Schema + migraciones una sola vez por worker (no en cada rerun de Streamlit)."""
    init_schema()
    ensure_migrations()
    return True


def _bootstrap_db() -> None:
    from evaluar.db_backend import using_postgres

    delays = (0.0, 1.5, 3.0, 5.0)
    last_exc: Exception | None = None
    for delay in delays:
        if delay:
            time_module.sleep(delay)
        try:
            _bootstrap_database(MIGRATION_VERSION)
            return
        except Exception as exc:
            last_exc = exc
            _bootstrap_database.clear()

    if not using_postgres():
        if last_exc:
            raise last_exc
        return

    st.error(
        "No se pudo conectar a la base de datos. Esperá unos segundos y tocá **Reintentar**. "
        "Si el problema continúa, revisá la configuración en Streamlit Secrets."
    )
    if st.button("Reintentar conexión", type="primary", key="bootstrap_retry"):
        _bootstrap_database.clear()
        st.rerun()
    st.markdown(
        """
        En [share.streamlit.io](https://share.streamlit.io) → tu app → **Settings** → **Secrets**,
        debe haber **una sola línea** como esta (con la URL que copiaste de Neon):

        ```
        DATABASE_URL = "postgresql://neondb_owner:TU_CONTRASEÑA@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require"
        ```

        **Checklist:**
        1. En Neon → **Dashboard** → activá **Pooled connection** → **Copy snippet** (contraseña visible).
        2. Pegá la URL **completa** entre comillas dobles.
        3. Sin espacios antes ni después del `=`.
        4. Si la contraseña tiene símbolos raros (`@`, `#`, `/`), en Neon generá una contraseña nueva (solo letras y números).
        5. **Save** en Secrets y **Reboot app**.
        """
    )
    if last_exc:
        with st.expander("Detalle del error (para soporte)"):
            st.code(str(last_exc))
    st.stop()


def _inject_brand_theme() -> None:
    """Fondo suave alineado al verde institucional (#044A30)."""
    st.markdown(
        f"""
        <style>
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main,
        section.main > div,
        .main .block-container {{
            background-color: {BG_MAIN} !important;
        }}
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {{
            background-color: {BG_SIDEBAR} !important;
        }}
        [data-testid="stHeader"] {{
            background-color: {BG_MAIN} !important;
        }}
        [data-testid="stToolbar"] {{
            background-color: transparent !important;
        }}
        details[data-testid="stExpander"],
        [data-testid="stDataFrame"],
        div[data-testid="stMetric"] {{
            background-color: {BG_SURFACE} !important;
            border: 1px solid {BORDER_SOFT};
            border-radius: 0.5rem;
        }}
        details[data-testid="stExpander"] summary {{
            background-color: {BG_SURFACE} !important;
        }}
        .stAlert {{
            border-radius: 0.5rem;
        }}
        .evaluar-metric {{
            background-color: {BG_SURFACE};
            border: 1px solid {BORDER_SOFT};
            border-radius: 0.5rem;
            padding: 0.85rem 0.5rem 0.75rem;
            text-align: center;
        }}
        .evaluar-metric-label {{
            font-size: 0.875rem;
            color: #475569;
            text-align: center;
            line-height: 1.3;
            margin-bottom: 0.35rem;
        }}
        .evaluar-metric-value {{
            font-size: 1.85rem;
            font-weight: 600;
            text-align: center;
            color: #0f172a;
            line-height: 1.2;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_card(label: str, value: str | int | float) -> None:
    st.markdown(
        f"""
        <div class="evaluar-metric">
            <div class="evaluar-metric-label">{html.escape(str(label))}</div>
            <div class="evaluar-metric-value">{html.escape(str(value))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_metrics_row(items: list[tuple[str, str | int | float]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        with col:
            _render_metric_card(label, value)


# No conectar a la DB en import-time: eso clava el redeploy de Streamlit Cloud
# cuando Neon está dormido. Se inicializa al entrar a main().
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


def _submissions_dataframe(
    submissions: list[dict],
    max_score: float,
    pass_min_score: float | None = None,
) -> pd.DataFrame:
    rows = []
    for s in submissions:
        score = float(s["score"])
        row = {
            "Apellido y nombre": s["student_name"],
            "DNI / Matrícula": s["student_dni"],
            f"Nota (0-{format_grade(max_score)})": round(float(score)),
            "Aciertos": s["correct_count"],
            "Errores": s["wrong_count"],
            "Sin responder": s["unanswered_count"],
            "Preguntas falladas": ", ".join(map(str, s["wrong_questions"])) or "—",
            "Fecha de envío": format_datetime(s["submitted_at"]),
        }
        status = passing_status(score, pass_min_score)
        if status is not None:
            row["Estado"] = status
        if s.get("earned_points") is not None and s.get("total_points") is not None:
            row["Puntos obtenidos"] = s["earned_points"]
            row["Puntos del examen"] = s["total_points"]
            row["Resumen"] = format_grading_summary(
                float(s["earned_points"]),
                float(s["total_points"]),
                max_score,
                float(s["score"]),
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _question_stats_dataframe(question_stats: list[dict]) -> pd.DataFrame:
    rows = []
    for stat in question_stats:
        rows.append(
            {
                "Pregunta": stat["order"],
                "Tipo": question_type_label(stat["type"]),
                "Aciertos": stat["correct"],
                "Errores": stat["incorrect"],
                "Sin responder": stat["unanswered"],
                "% de acierto": stat["success_rate"],
            }
        )
    return pd.DataFrame(rows)


def _export_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Notas")
    return buffer.getvalue()


def _render_local_backup_notice() -> None:
    st.info(
        "**Guardá todo en tu computadora.** EvaluAR usa almacenamiento temporal en la nube: "
        "descargá y archivá cada **examen** (archivo `.json`) y cada **planilla de notas** "
        "(Excel o CSV) en tu disco. Así conservás tus claves de respuestas y las notas "
        "aunque la app se reinicie."
    )


def _render_exam_backup_download(
    exam: dict,
    *,
    label: str = "Descargar examen (.json)",
    key: str | None = None,
) -> None:
    st.download_button(
        label,
        data=exam_backup_bytes(exam),
        file_name=exam_backup_filename(exam),
        mime="application/json",
        use_container_width=True,
        key=key or f"backup_exam_{exam['id']}",
    )


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
        st.caption(f"Código del examen: **`{code}`** (copiá también la URL desde el navegador)")

    code_js = json.dumps(code)
    share_js = json.dumps(share_url)
    base_js = json.dumps(base_url)
    message_js = json.dumps(
        "Examen en papel. Después cargá tus respuestas en EvaluAR:\n"
        + (f"{share_url or base_url}\n" if (share_url or base_url) else "")
        + f"Código del examen: {code}\n"
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
    copy_feedback_js = """
            function markCopied(btn, doneLabel) {
              if (!btn.dataset.originalLabel) {
                btn.dataset.originalLabel = btn.innerText;
                btn.dataset.originalStyle = btn.getAttribute("style") || "";
              }
              btn.innerText = doneLabel || "✓ Copiado";
              btn.style.background = "#dcfce7";
              btn.style.borderColor = "#16a34a";
              btn.style.color = "#166534";
              btn.style.fontWeight = "600";
              setTimeout(function() {
                btn.innerText = btn.dataset.originalLabel;
                btn.setAttribute("style", btn.dataset.originalStyle);
              }, 2000);
            }
            async function copyText(btn, text, emptyMsg) {
              if (!text) {
                alert(emptyMsg || "No hay contenido para copiar.");
                return;
              }
              try {
                await navigator.clipboard.writeText(text);
                markCopied(btn);
              } catch (error) {
                alert("No se pudo copiar. Probá de nuevo.");
              }
            }
    """

    if share_url:
        qr_b64 = base64.b64encode(_qr_png_bytes(share_url)).decode("ascii")
        st.caption(
            f"**Link para alumnos** (con código incluido): `{share_url}` — "
            "el alumno abre EvaluAR y ya entra a cargar respuestas."
        )
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
                  Copiar link para alumnos
                </button>
                <button type="button" id="copy-msg-{html_id}" style="{btn_primary}">
                  Copiar mensaje WhatsApp
                </button>
                <button type="button" id="copy-qr-{html_id}" style="{btn_outline}">
                  Copiar QR
                </button>
                <a id="download-qr-{html_id}" download="evaluar-{code}.png"
                   href="data:image/png;base64,{qr_b64}"
                   onclick="markCopied(this, '✓ Descargado');"
                   style="{btn_outline}display:block;text-align:center;text-decoration:none;">
                  Descargar QR (PNG)
                </a>
              </div>
            </div>
            <script>
            {copy_feedback_js}
            document.getElementById("copy-code-{html_id}").onclick = function() {{
                copyText(this, {code_js});
            }};
            document.getElementById("copy-url-{html_id}").onclick = function() {{
                copyText(this, {base_js}, "Copiá la URL desde la barra del navegador.");
            }};
            document.getElementById("copy-link-{html_id}").onclick = function() {{
                copyText(this, {share_js}, "No hay link directo disponible.");
            }};
            document.getElementById("copy-msg-{html_id}").onclick = function() {{
                copyText(this, {message_js});
            }};
            document.getElementById("copy-qr-{html_id}").onclick = async function() {{
                try {{
                    const response = await fetch(document.getElementById("qr-{html_id}").src);
                    const blob = await response.blob();
                    await navigator.clipboard.write([new ClipboardItem({{ "image/png": blob }})]);
                    markCopied(this);
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
            {copy_feedback_js}
            document.getElementById("copy-code-{html_id}").onclick = function() {{
                copyText(this, {code_js});
            }};
            document.getElementById("copy-msg-{html_id}").onclick = function() {{
                copyText(this, {message_js});
            }};
            </script>
            """,
            height=120,
        )


def _render_session_access_control(active: dict, teacher_id: str) -> None:
    session_open = is_session_open(active)
    st.markdown("#### Cerrar código del examen")
    if session_open:
        st.warning(
            "El código **está abierto**: los alumnos pueden seguir cargando respuestas. "
            "Cuando la comisión terminó, usá el botón de abajo."
        )
        if st.button(
            "Cerrar código — no más respuestas de alumnos",
            type="primary",
            use_container_width=True,
            key=f"close_session_{active['id']}",
        ):
            set_session_active(active["id"], teacher_id, False)
            st.success("Código cerrado. Los alumnos ya no pueden enviar respuestas.")
            st.rerun()
    else:
        st.success(
            "Código **cerrado**. Los alumnos ya no pueden cargar respuestas nuevas."
        )
        if st.button(
            "Reabrir código para permitir más cargas",
            use_container_width=True,
            key=f"reopen_session_{active['id']}",
        ):
            set_session_active(active["id"], teacher_id, True)
            st.success("Código reabierto.")
            st.rerun()


def _render_session_delete(active: dict, teacher_id: str) -> None:
    st.markdown("#### Eliminar código")
    st.caption(
        "Borrá códigos de **prueba** sin eliminar el examen. "
        "Después podés generar el código definitivo del examen."
    )
    submissions = int(active.get("submission_count") or 0)
    if submissions:
        st.warning(
            f"Este código tiene **{submissions} respuesta(s)** cargadas. "
            "Al eliminarlo se pierden; descargá la planilla antes si las necesitás."
        )
    confirm = st.text_input(
        f"Escribí **{active['code']}** para confirmar",
        key=f"delete_session_confirm_{active['id']}",
    )
    if st.button(
        "Eliminar este código (no borra el examen)",
        use_container_width=True,
        key=f"delete_session_btn_{active['id']}",
    ):
        if confirm.strip().upper() != str(active["code"]).upper():
            st.error(f"Escribí {active['code']} para confirmar.")
        else:
            with st.spinner("Eliminando código..."):
                try:
                    deleted = delete_session(active["id"], teacher_id)
                except Exception as exc:
                    st.error(f"No se pudo eliminar el código: {exc}")
                    return
            if not deleted:
                st.error("No se pudo eliminar el código.")
            else:
                if st.session_state.get("session_id") == active["id"]:
                    st.session_state.session_id = None
                if st.session_state.get("flash_session_code") == active["code"]:
                    st.session_state.flash_session_code = None
                st.session_state.pop(f"delete_session_confirm_{active['id']}", None)
                st.success(f"Código {active['code']} eliminado.")
                st.rerun()


def ensure_state() -> None:
    defaults = {
        "teacher": None,
        "page": "home",
        "exam_id": None,
        "session_id": None,
        "student_code": None,
        "student_step": "identify",
        "student_result": None,
        "student_exam_payload": None,
        "student_name": "",
        "student_dni": "",
        "student_page_num": 1,
        "student_answer_code": None,
        "student_answers": {},
        "answer_key_draft": "",
        "exam_wizard_step": "general",
        "exam_wizard_general": {},
        "exam_wizard_drafts": [],
        "exam_question_drafts": None,
        "exam_questions_source_id": None,
        "exam_wizard_last_page": None,
        "exam_wizard_page": 1,
        "last_created_session_code": None,
        "flash_session_code": None,
        "exam_wizard_mode": "create",
        "edit_exam_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _get_student_session_payload(code: str) -> dict | None:
    """Cachea examen/preguntas en session_state para no pegarle a Neon en cada click."""
    code = code.strip().upper()
    cached = st.session_state.get("student_exam_payload")
    if (
        isinstance(cached, dict)
        and cached.get("code") == code
        and cached.get("payload")
    ):
        return cached["payload"]
    payload = get_session_by_code(code)
    if payload:
        st.session_state.student_exam_payload = {"code": code, "payload": payload}
    else:
        st.session_state.student_exam_payload = None
    return payload


def _clear_student_answer_widgets() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("ans_"):
            del st.session_state[key]
    st.session_state.student_answers = {}


def _sync_student_answer_state(code: str) -> None:
    """Limpia respuestas previas al cambiar de código de examen."""
    code = code.strip().upper()
    if st.session_state.get("student_answer_code") != code:
        _clear_student_answer_widgets()
        st.session_state.student_answer_code = code
    if not isinstance(st.session_state.get("student_answers"), dict):
        st.session_state.student_answers = {}


def _store_student_choice(order: int) -> None:
    value = st.session_state.get(f"ans_{order}")
    store = st.session_state.setdefault("student_answers", {})
    order_key = str(order)
    if value is not None and str(value).strip():
        store[order_key] = str(value)
    else:
        store.pop(order_key, None)


def _store_student_matching_item(order: int, left_key: str) -> None:
    letter = st.session_state.get(f"ans_{order}_{left_key}")
    store = st.session_state.setdefault("student_answers", {})
    order_key = str(order)
    matching: dict[str, str] = {}
    if order_key in store:
        try:
            parsed = json.loads(store[order_key])
            if isinstance(parsed, dict):
                matching = parsed
        except (json.JSONDecodeError, TypeError):
            matching = {}
    if letter:
        matching[left_key] = str(letter)
    else:
        matching.pop(left_key, None)
    if matching:
        store[order_key] = json.dumps(matching)
    else:
        store.pop(order_key, None)


def _flush_student_page_answers(visible_questions: list) -> None:
    """Respaldo: sincroniza widgets visibles al almacén persistente."""
    for question in visible_questions:
        order = question["order"]
        qtype = question["type"]
        if qtype in ("MULTIPLE_CHOICE", "TRUE_FALSE"):
            _store_student_choice(order)
            continue
        _, pairs = _load_question_options(question["options"], qtype)
        for pair in pairs:
            left_key = str(pair["left"]).lower()
            _store_student_matching_item(order, left_key)


def _prepare_student_question_widget(question: dict) -> None:
    """Restaura en el widget una respuesta guardada al volver a una página."""
    order = question["order"]
    qtype = question["type"]
    stored = st.session_state.get("student_answers", {}).get(str(order))
    if not stored:
        return
    if qtype in ("MULTIPLE_CHOICE", "TRUE_FALSE"):
        key = f"ans_{order}"
        if key not in st.session_state:
            st.session_state[key] = stored
        return
    try:
        matching = json.loads(stored)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(matching, dict):
        return
    for left_key, letter in matching.items():
        widget_key = f"ans_{order}_{left_key}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = letter


def _render_student_question(question: dict) -> None:
    order = question["order"]
    st.markdown(f"**Pregunta {order}**")
    if question.get("prompt"):
        st.caption(question["prompt"])
    _prepare_student_question_widget(question)
    qtype = question["type"]
    if qtype == "MULTIPLE_CHOICE":
        mc_options, _ = _load_question_options(question["options"], qtype)
        st.radio(
            "Opción",
            mc_options,
            key=f"ans_{order}",
            horizontal=True,
            index=None,
            on_change=_store_student_choice,
            args=(order,),
        )
    elif qtype == "TRUE_FALSE":
        st.radio(
            "Respuesta",
            ["V", "F"],
            format_func=lambda x: "Verdadero" if x == "V" else "Falso",
            key=f"ans_{order}",
            horizontal=True,
            index=None,
            on_change=_store_student_choice,
            args=(order,),
        )
    else:
        targets, pairs = _load_question_options(question["options"], qtype)
        for pair in pairs:
            left_key = str(pair["left"]).lower()
            st.selectbox(
                f"Ítem **{pair['left']}** →",
                targets,
                key=f"ans_{order}_{left_key}",
                index=None,
                placeholder="Seleccioná",
                on_change=_store_student_matching_item,
                args=(order, left_key),
            )


def _collect_student_answers(questions: list, visible: list | None = None) -> dict[str, str]:
    """Junta respuestas desde el almacén persistente (sobrevive al cambio de página)."""
    if visible:
        _flush_student_page_answers(visible)
    store = st.session_state.get("student_answers") or {}
    return {str(question["order"]): store.get(str(question["order"]), "") for question in questions}


def _clear_question_widget_state() -> None:
    """Limpia widgets temporales del asistente para no mezclar preguntas entre exámenes."""
    keys_to_drop = [
        key
        for key in st.session_state.keys()
        if key.startswith("q") and (
            "_type_label" in key
            or "_option_count" in key
            or "_mc_answer" in key
            or "_vf_answer" in key
            or "_target_count" in key
            or "_item_count" in key
            or "_points" in key
            or "_match_" in key
        )
    ]
    for key in keys_to_drop:
        st.session_state.pop(key, None)


@st.cache_data(show_spinner=False)
def _logo_base64() -> str:
    if LOGO_PATH.is_file():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return ""


@st.cache_data(ttl=60, show_spinner=False)
def _cached_usage_count() -> int:
    return get_usage_count()


def _render_db_error(context: str, exc: Exception | None = None, retry_key: str = "db_retry") -> None:
    st.error(
        f"No se pudo {context}. La base de datos puede estar reconectando "
        "(normal tras unos segundos de inactividad). **Esperá 5 segundos y tocá Reintentar.**"
    )
    if exc is not None:
        with st.expander("Detalle técnico"):
            st.code(str(exc))
    if st.button("Reintentar", type="primary", key=retry_key):
        st.rerun()


def _usage_count_for_sidebar() -> int:
    cached = st.session_state.get("usage_count_display")
    if cached is not None:
        return int(cached)
    try:
        total = _cached_usage_count()
    except Exception:
        return int(cached or 0)
    st.session_state.usage_count_display = total
    return total


def _bump_usage_count() -> int:
    try:
        total = increment_usage_count()
    except Exception:
        return int(st.session_state.get("usage_count_display") or 0)
    st.session_state.usage_count_display = total
    try:
        _cached_usage_count.clear()
    except Exception:
        pass
    return total


def _wizard_preview_total(general: dict, question_count: int) -> float:
    """Puntaje total sin validar todas las preguntas en cada rerun."""
    if general.get("scoring_mode", "equal") == "equal":
        return float(question_count)
    drafts = st.session_state.get("exam_question_drafts") or []
    if len(drafts) >= question_count:
        return sum(float(d.get("points", 1)) for d in drafts[:question_count])
    return float(question_count)


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
            '<div style="background:#044A30;color:white;width:80px;height:80px;'
            'border-radius:50%;display:flex;align-items:center;justify-content:center;'
            'font-weight:700;font-size:1.75rem;">E</div>'
        )

    st.markdown(
        f"""
        <style>
        .evaluar-logo {{
            display: block;
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid #044A30;
            box-shadow: 0 2px 8px rgba(4, 74, 48, 0.15);
        }}
        </style>
        <div style="display:flex;align-items:center;gap:18px;margin-bottom:10px;">
          {logo_html}
          <div>
            <div style="font-size:2rem;font-weight:700;color:#044A30;line-height:1.15;">EvaluAR</div>
            <div style="color:#64748b;font-size:1.05rem;line-height:1.35;margin-top:2px;">
              Examen en papel. Corrección digital.
            </div>
            <div style="color:#94a3b8;font-size:0.92rem;margin-top:4px;line-height:1.35;">{obs} · {inst}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    st.sidebar.title("Navegación")
    if st.session_state.teacher:
        st.sidebar.success(f"Cátedra o Docente: {st.session_state.teacher['name']}")
        if st.sidebar.button("Panel docente", use_container_width=True):
            st.session_state.page = "panel"
            st.rerun()
        if st.sidebar.button("Nuevo examen", use_container_width=True):
            _reset_exam_wizard()
            st.session_state.page = "new_exam"
            st.rerun()
        if st.sidebar.button("Cerrar sesión", use_container_width=True):
            _reset_exam_wizard()
            st.session_state.teacher = None
            st.session_state.page = "home"
            st.rerun()
    else:
        if st.sidebar.button("Acceso docente", use_container_width=True):
            st.session_state.page = "auth"
            st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("**Acceso alumno**")
    st.sidebar.caption("Ingresá el código del examen o abrí el link del docente.")
    code = st.sidebar.text_input("Código del examen", placeholder="Ej. JT7MH2GD", key="sidebar_student_code")
    if st.sidebar.button("Cargar mis respuestas", use_container_width=True) and code.strip():
        st.session_state.student_code = code.strip().upper()
        st.session_state.page = "student"
        st.session_state.student_step = "identify"
        st.session_state.student_result = None
        st.session_state.student_exam_payload = None
        st.session_state.student_page_num = 1
        st.session_state.student_answer_code = None
        _clear_student_answer_widgets()
        st.rerun()

    st.sidebar.divider()
    usage_total = _usage_count_for_sidebar()
    st.sidebar.caption(f"**{usage_total}** veces se utilizó EvaluAR")


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
            "Pensado para carreras con alto volumen: 100 alumnos, 50 preguntas o más, "
            "opción múltiple, V/F y emparejamiento."
        )

    st.divider()
    st.subheader("Soy alumno")
    st.markdown(
        "Después del examen en papel, ingresá el **código** que te dio el docente "
        "(o abrí el link que te compartió)."
    )
    student_code = st.text_input(
        "Código del examen",
        placeholder="Ej. JT7MH2GD",
        key="home_student_code",
    )
    if st.button("Ingresar y cargar mis respuestas", type="primary"):
        if not student_code.strip():
            st.error("Ingresá el código del examen.")
        else:
            st.session_state.student_code = student_code.strip().upper()
            st.session_state.page = "student"
            st.session_state.student_step = "identify"
            st.session_state.student_result = None
            st.session_state.student_exam_payload = None
            st.session_state.student_page_num = 1
            st.session_state.student_answer_code = None
            _clear_student_answer_widgets()
            st.rerun()


def page_auth() -> None:
    st.subheader("Acceso docente")
    tab_login, tab_register = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with tab_login:
        name = st.text_input(
            "Nombre de cátedra o docente",
            placeholder="Ej. Inmunología-Medicina-UCCuyo",
            key="login_name",
        )
        pin = st.text_input("PIN", type="password", key="login_pin")
        if st.button("Ingresar", type="primary"):
            try:
                teacher = login_teacher(name, pin)
            except Exception as exc:
                _render_db_error("iniciar sesión", exc, retry_key="login_retry")
            else:
                if not teacher:
                    st.error("Credenciales incorrectas.")
                else:
                    _bump_usage_count()
                    st.session_state.teacher = teacher
                    st.session_state.page = "panel"
                    st.success("Sesión iniciada.")
                    st.rerun()

    with tab_register:
        st.caption(
            "Si son varios docentes en la misma cátedra, creen **una sola cuenta** compartida. "
            "Usá un nombre único con materia e institución (ej. «Anatomía-UCCuyo»)."
        )
        name = st.text_input(
            "Nombre de cátedra o docente",
            placeholder="Ej. Inmunología-Medicina-UCCuyo",
            key="register_name",
        )
        pin = st.text_input("PIN (mínimo 4 caracteres)", type="password", key="register_pin")
        if st.button("Crear cuenta", type="primary"):
            if not name.strip():
                st.error("Ingresá un nombre para la cátedra o docente.")
            elif len(pin.strip()) < 4:
                st.error("El PIN debe tener al menos 4 caracteres.")
            else:
                try:
                    teacher = register_teacher(name, pin)
                    _bump_usage_count()
                    st.session_state.teacher = teacher
                    st.session_state.page = "panel"
                    st.success("Cuenta creada.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"No se pudo registrar: {exc}")


def page_panel() -> None:
    if not st.session_state.teacher:
        st.session_state.page = "auth"
        st.rerun()
        return

    st.subheader("Panel docente")
    _render_local_backup_notice()

    if st.button("➕ Nuevo examen"):
        _reset_exam_wizard()
        st.session_state.page = "new_exam"
        st.rerun()

    try:
        exams = list_exams(st.session_state.teacher["id"])
    except Exception as exc:
        _render_db_error("cargar tus exámenes", exc, retry_key="panel_retry")
        return

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
                col_a, col_b, col_c, col_d = st.columns(4)
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
                with col_d:
                    if st.button("Eliminar", key=f"del_exam_{exam['id']}", use_container_width=True):
                        st.session_state[f"confirm_delete_exam_{exam['id']}"] = True
                try:
                    full_exam = get_exam(exam["id"], st.session_state.teacher["id"])
                except Exception:
                    full_exam = None
                if full_exam:
                    _render_exam_backup_download(
                        full_exam,
                        label="Guardar examen en mi computadora (.json)",
                    )
                if st.session_state.get(f"confirm_delete_exam_{exam['id']}"):
                    st.warning(
                        "Se eliminará este examen, sus códigos y las respuestas de alumnos. "
                        "Descargá el `.json` y la planilla antes si los necesitás."
                    )
                    confirm = st.text_input(
                        "Escribí ELIMINAR para confirmar",
                        key=f"delete_exam_confirm_{exam['id']}",
                    )
                    c_ok, c_cancel = st.columns(2)
                    with c_ok:
                        if st.button(
                            "Confirmar eliminación",
                            type="primary",
                            use_container_width=True,
                            key=f"delete_exam_ok_{exam['id']}",
                        ):
                            if confirm.strip().upper() != "ELIMINAR":
                                st.error("Escribí ELIMINAR para confirmar.")
                            else:
                                with st.spinner("Eliminando examen..."):
                                    try:
                                        deleted = delete_exam(
                                            exam["id"],
                                            st.session_state.teacher["id"],
                                        )
                                    except Exception as exc:
                                        st.error(f"No se pudo eliminar el examen: {exc}")
                                        deleted = None
                                if deleted:
                                    if st.session_state.get("exam_id") == exam["id"]:
                                        st.session_state.exam_id = None
                                        st.session_state.session_id = None
                                    st.session_state.pop(
                                        f"confirm_delete_exam_{exam['id']}", None
                                    )
                                    st.session_state.pop(
                                        f"delete_exam_confirm_{exam['id']}", None
                                    )
                                    st.success(f"Examen «{deleted['title']}» eliminado.")
                                    st.rerun()
                                elif deleted is not None:
                                    st.error("No se pudo eliminar el examen.")
                    with c_cancel:
                        if st.button(
                            "Cancelar",
                            use_container_width=True,
                            key=f"delete_exam_cancel_{exam['id']}",
                        ):
                            st.session_state.pop(f"confirm_delete_exam_{exam['id']}", None)
                            st.session_state.pop(f"delete_exam_confirm_{exam['id']}", None)
                            st.rerun()

    with st.expander("Restaurar examen desde tu computadora"):
        st.caption(
            "Si tenés un archivo `.json` que descargaste antes, podés volver a cargar "
            "el examen y su clave de respuestas."
        )
        uploaded = st.file_uploader(
            "Archivo de examen",
            type=["json"],
            key="import_exam_backup",
        )
        if uploaded is not None and st.button("Importar examen", type="primary"):
            try:
                payload = parse_exam_backup(uploaded.read())
                new_id = create_exam(st.session_state.teacher["id"], **payload)
                st.session_state.exam_id = new_id
                st.session_state.flash_download_exam = True
                st.session_state.page = "exam_detail"
                st.success("Examen importado. Descargalo de nuevo para tener una copia actualizada.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"No se pudo importar el examen: {exc}")

    with st.expander("Limpiar datos de prueba"):
        st.warning(
            "Elimina **todos** los exámenes, códigos del examen y respuestas de alumnos. "
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
    scoring_mode = st.session_state.exam_wizard_general.get("scoring_mode", "equal")
    if scoring_mode == "manual":
        st.number_input(
            "Puntaje de esta pregunta",
            min_value=0.25,
            max_value=100.0,
            value=float(st.session_state.get(f"q{question_number}_points", 1.0)),
            step=0.25,
            key=f"q{question_number}_points",
        )

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
                key=f"q{question_number}_target_count",
            )
        with col2:
            item_count = st.selectbox(
                "Cantidad de ítems a emparejar",
                [3, 4, 5, 6],
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
    scoring_mode = st.session_state.exam_wizard_general.get("scoring_mode", "equal")
    draft = {
        "order": question_number,
        "type": qtype,
        "points": 1.0 if scoring_mode == "equal" else float(
            st.session_state.get(f"q{question_number}_points", 1.0)
        ),
    }

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


def _sync_draft_to_widgets(question_number: int, draft: dict) -> None:
    """Carga un borrador guardado en los widgets de una pregunta."""
    st.session_state[f"q{question_number}_type_label"] = TYPE_LABELS.get(
        draft["type"], "Opción múltiple"
    )
    st.session_state[f"q{question_number}_points"] = float(draft.get("points", 1))
    if draft["type"] == "MULTIPLE_CHOICE":
        st.session_state[f"q{question_number}_option_count"] = int(draft.get("option_count", 5))
        st.session_state[f"q{question_number}_mc_answer"] = str(draft.get("mc_answer", "A"))
    elif draft["type"] == "TRUE_FALSE":
        st.session_state[f"q{question_number}_vf_answer"] = str(draft.get("vf_answer", "V"))
    elif draft["type"] == "MATCHING":
        item_count = int(draft.get("item_count", 3))
        st.session_state[f"q{question_number}_target_count"] = int(draft.get("target_count", 6))
        st.session_state[f"q{question_number}_item_count"] = item_count
        answers = draft.get("matching_answers") or {}
        for label in item_labels(item_count):
            st.session_state[f"q{question_number}_match_{label}"] = answers.get(label, "A")


def _sync_widgets_to_draft(question_number: int) -> None:
    """Guarda los widgets visibles de una pregunta en el borrador maestro."""
    if f"q{question_number}_type_label" not in st.session_state:
        return
    draft = _collect_question_draft(question_number)
    drafts = st.session_state.exam_question_drafts
    if drafts is None:
        drafts = []
        st.session_state.exam_question_drafts = drafts
    while len(drafts) < question_number:
        drafts.append(default_question_draft(len(drafts) + 1))
    drafts[question_number - 1] = draft


def _flush_question_page_to_drafts(start: int, end: int) -> None:
    for number in range(start, end + 1):
        _sync_widgets_to_draft(number)


def _ensure_exam_question_drafts(question_count: int) -> None:
    drafts = st.session_state.get("exam_question_drafts")
    if not drafts:
        st.session_state.exam_question_drafts = [
            default_question_draft(number) for number in range(1, question_count + 1)
        ]
        return
    while len(drafts) < question_count:
        drafts.append(default_question_draft(len(drafts) + 1))
    if len(drafts) > question_count:
        st.session_state.exam_question_drafts = drafts[:question_count]


def _load_exam_drafts_from_db(exam_id: str, teacher_id: str) -> bool:
    exam = get_exam(exam_id, teacher_id)
    if not exam:
        return False
    _clear_question_widget_state()
    st.session_state.exam_question_drafts = drafts_from_exam_questions(exam["questions"])
    st.session_state.exam_questions_source_id = exam_id
    st.session_state.exam_wizard_last_page = None
    return True


def _wizard_page_for_question(question_number: int) -> int:
    return (question_number - 1) // QUESTIONS_PER_PAGE + 1


def _prepare_question_page(question_count: int, current_page: int) -> tuple[int, int]:
    """Sincroniza borradores ↔ widgets al cambiar de página del asistente."""
    _ensure_exam_question_drafts(question_count)
    page_size = QUESTIONS_PER_PAGE
    total_pages = max(1, (question_count + page_size - 1) // page_size)
    current_page = max(1, min(current_page, total_pages))
    start = (current_page - 1) * page_size + 1
    end = min(question_count, start + page_size - 1)

    last_page = st.session_state.get("exam_wizard_last_page")
    if last_page is not None and last_page != current_page:
        prev_start = (last_page - 1) * page_size + 1
        prev_end = min(question_count, prev_start + page_size - 1)
        _flush_question_page_to_drafts(prev_start, prev_end)

    if last_page != current_page:
        drafts = st.session_state.exam_question_drafts or []
        for number in range(start, end + 1):
            if number <= len(drafts):
                _sync_draft_to_widgets(number, drafts[number - 1])
        st.session_state.exam_wizard_last_page = current_page

    return start, end


def _apply_equal_scoring_to_drafts(question_count: int) -> None:
    """En modo automático, todas las preguntas valen 1 pt (también las de otras páginas)."""
    _ensure_exam_question_drafts(question_count)
    drafts = st.session_state.exam_question_drafts or []
    for draft in drafts[:question_count]:
        draft["points"] = 1.0


def _collect_all_question_drafts(question_count: int, start: int, end: int) -> list[dict]:
    _flush_question_page_to_drafts(start, end)
    drafts = st.session_state.exam_question_drafts or []
    if len(drafts) < question_count:
        _ensure_exam_question_drafts(question_count)
        drafts = st.session_state.exam_question_drafts or []
    scoring_mode = (st.session_state.get("exam_wizard_general") or {}).get(
        "scoring_mode", "equal"
    )
    if scoring_mode == "equal":
        _apply_equal_scoring_to_drafts(question_count)
        drafts = st.session_state.exam_question_drafts or []
    return drafts[:question_count]


def _begin_edit_exam(exam_id: str, teacher_id: str) -> None:
    if not _load_exam_drafts_from_db(exam_id, teacher_id):
        return
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
        "scoring_mode": exam.get("scoring_mode") or "equal",
        "pass_min_score": (
            float(exam["pass_min_score"])
            if exam.get("pass_min_score") is not None
            else None
        ),
    }
    st.session_state.exam_wizard_step = "general"
    st.session_state.exam_wizard_page = 1


def _reset_exam_wizard() -> None:
    st.session_state.exam_wizard_step = "general"
    st.session_state.exam_wizard_general = {}
    st.session_state.exam_wizard_page = 1
    st.session_state.exam_wizard_mode = "create"
    st.session_state.edit_exam_id = None
    st.session_state.exam_question_drafts = None
    st.session_state.exam_questions_source_id = None
    st.session_state.exam_wizard_last_page = None
    _clear_question_widget_state()


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
            placeholder="Examen 2",
            value=preset.get("title", ""),
            help="Ej. Examen 1, Final, Recuperatorio",
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
                "Fecha del examen *",
                value=preset_date,
                format="DD/MM/YYYY",
                help="Elegí día, mes y año desde el calendario.",
            )
        with col_time:
            exam_time = st.time_input(
                "Hora del examen",
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
            wizard_key = st.session_state.get("edit_exam_id") if editing else "create"
            question_count = st.number_input(
                "Cantidad total de preguntas *",
                min_value=1,
                max_value=200,
                value=int(preset.get("question_count", 50)),
                key=f"wizard_{wizard_key}_question_count",
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
                "Mostrar al alumno el número de preguntas falladas",
                value=bool(preset.get("show_detail", True)),
                help="Si está activo, después de enviar verá qué números falló u omitió.",
            )

        preset_max = float(preset.get("max_score", 10.0))
        preset_has_pass = "pass_min_score" in preset and preset.get("pass_min_score") is not None
        use_pass_min = st.checkbox(
            "Definir nota mínima de aprobación",
            value=preset_has_pass if preset else True,
            help="Ej.: nota máxima 10 y aprobar con 6 (60% del puntaje total).",
        )
        pass_min_score = None
        if use_pass_min:
            default_pass = preset.get("pass_min_score")
            if default_pass is None:
                default_pass = default_pass_min_score(preset_max)
            pass_min_score = st.number_input(
                "Nota mínima para aprobar",
                min_value=0.0,
                max_value=float(max_score),
                value=min(float(default_pass), float(max_score)),
                step=0.5,
            )
            if pass_min_score > max_score:
                st.error("La nota mínima no puede superar la nota máxima.")
            else:
                pct = (pass_min_score / max_score * 100) if max_score > 0 else 0
                st.caption(
                    f"Se considera **aprobado** con **{format_score(pass_min_score)}** o más "
                    f"({pct:.0f}% de {format_score(max_score)})."
                )

        scoring_options = {
            "Automático (1 punto por pregunta)": "equal",
            "Manual (definís el puntaje de cada pregunta)": "manual",
        }
        preset_mode = preset.get("scoring_mode", "equal")
        scoring_label = st.radio(
            "Puntaje del examen",
            list(scoring_options.keys()),
            index=0 if preset_mode == "equal" else 1,
            help=(
                "La nota final siempre va de 0 a la nota máxima. "
                "El sistema calcula: (puntos obtenidos ÷ puntos totales del examen) × nota máxima."
            ),
            key=f"wizard_{st.session_state.get('edit_exam_id') if editing else 'create'}_scoring_label",
        )
        scoring_mode = scoring_options[scoring_label]
        if scoring_mode == "equal":
            st.caption(
                f"Modo automático: **{int(question_count)} preguntas = {int(question_count)} puntos** "
                f"→ nota de 0 a {max_score}."
            )
        else:
            st.caption(
                "Modo manual: en el paso 2 asignás cuántos puntos vale cada pregunta. "
                f"La suma de puntos se convierte a nota de 0 a {max_score}."
            )

        st.info(
            "En el siguiente paso configurarás **cada pregunta**: tipo, cantidad de opciones "
            "(si corresponde), respuesta correcta y —si elegiste manual— su puntaje."
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
                elif use_pass_min and pass_min_score is not None and pass_min_score > max_score:
                    st.error("La nota mínima de aprobación no puede ser mayor que la nota máxima.")
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
                        "pass_min_score": float(pass_min_score) if use_pass_min and pass_min_score is not None else None,
                        "show_detail": show_detail,
                        "scoring_mode": scoring_mode,
                    }
                    if editing:
                        if (
                            st.session_state.get("exam_questions_source_id")
                            != st.session_state.edit_exam_id
                        ):
                            _load_exam_drafts_from_db(
                                st.session_state.edit_exam_id,
                                st.session_state.teacher["id"],
                            )
                        drafts = list(st.session_state.exam_question_drafts or [])
                        if int(question_count) > len(drafts):
                            while len(drafts) < int(question_count):
                                drafts.append(default_question_draft(len(drafts) + 1))
                        elif int(question_count) < len(drafts):
                            drafts = drafts[: int(question_count)]
                        st.session_state.exam_question_drafts = drafts
                    else:
                        if int(question_count) != previous_count:
                            _ensure_exam_question_drafts(int(question_count))
                        elif not st.session_state.get("exam_question_drafts"):
                            _ensure_exam_question_drafts(int(question_count))
                    if scoring_mode == "equal":
                        _apply_equal_scoring_to_drafts(int(question_count))
                    st.session_state.exam_wizard_step = "questions"
                    st.session_state.exam_wizard_page = 1
                    st.session_state.exam_wizard_last_page = None
                    st.rerun()

    else:
        general = st.session_state.exam_wizard_general
        if not general:
            st.session_state.exam_wizard_step = "general"
            st.rerun()
            return

        if (
            editing
            and st.session_state.get("exam_questions_source_id")
            != st.session_state.get("edit_exam_id")
        ):
            _load_exam_drafts_from_db(
                st.session_state.edit_exam_id,
                st.session_state.teacher["id"],
            )

        question_count = int(general["question_count"])
        total_pages = max(1, (question_count + QUESTIONS_PER_PAGE - 1) // QUESTIONS_PER_PAGE)
        current_page = int(st.session_state.exam_wizard_page)
        current_page = max(1, min(current_page, total_pages))
        start, end = _prepare_question_page(question_count, current_page)

        st.markdown("### 2. Clave de respuestas — pregunta por pregunta")
        preview_total = _wizard_preview_total(general, question_count)

        st.info(
            f"**Puntaje total del examen: {format_score(preview_total)} pts** · "
            f"Nota final = (puntos del alumno ÷ {format_score(preview_total)}) × "
            f"{general['max_score']} (escala 0 a {general['max_score']})."
        )
        st.caption(
            f"{general['career']} · {general['subject']} · Año {general['career_year']} · "
            f"{general['title']} · "
            f"{format_exam_schedule(general.get('exam_date'), general.get('exam_time')) or 'Sin fecha'} · "
            f"{question_count} preguntas · "
            f"{'1 pt/pregunta' if general.get('scoring_mode') == 'equal' else 'puntaje manual'}"
        )

        st.progress(min(current_page / total_pages, 1.0))
        st.caption(
            f"Página **{current_page}** de **{total_pages}** · "
            f"preguntas **{start}–{end}** de **{question_count}**"
        )

        focus_question = st.session_state.pop("wizard_focus_question", None)
        for number in range(start, end + 1):
            with st.expander(
                f"Pregunta {number}",
                expanded=(focus_question == number),
            ):
                _render_question_editor(number)

        nav1, nav2, jump_num, jump_btn, nav3, nav4 = st.columns([1, 1, 1, 0.5, 1, 1])
        with nav1:
            if st.button("← Datos generales", use_container_width=True):
                _flush_question_page_to_drafts(start, end)
                st.session_state.exam_wizard_step = "general"
                st.session_state.exam_wizard_last_page = None
                st.rerun()
        with nav2:
            if st.button(
                "← Página anterior",
                use_container_width=True,
                disabled=current_page <= 1,
            ):
                _flush_question_page_to_drafts(start, end)
                st.session_state.exam_wizard_page = current_page - 1
                st.rerun()
        with jump_num:
            goto_question = st.number_input(
                "Ir a pregunta",
                min_value=1,
                max_value=question_count,
                value=start,
                step=1,
                key="wizard_goto_question",
            )
        with jump_btn:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            goto_clicked = st.button("Ir →", use_container_width=True, key="wizard_goto_btn")
        with nav3:
            if st.button(
                "Página siguiente →",
                use_container_width=True,
                disabled=current_page >= total_pages,
            ):
                _flush_question_page_to_drafts(start, end)
                st.session_state.exam_wizard_page = current_page + 1
                st.rerun()
        with nav4:
            save_label = "Guardar cambios" if editing else "Crear examen"
            if st.button(save_label, type="primary", use_container_width=True):
                try:
                    drafts = _collect_all_question_drafts(question_count, start, end)
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
                            general.get("pass_min_score"),
                            general["show_detail"],
                            general.get("scoring_mode", "equal"),
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
                            general.get("pass_min_score"),
                            general["show_detail"],
                            general.get("scoring_mode", "equal"),
                            questions,
                        )
                        st.session_state.exam_id = exam_id
                        success_msg = "Examen creado."
                        st.session_state.flash_download_exam = True
                    _reset_exam_wizard()
                    st.session_state.page = "exam_detail"
                    st.success(success_msg)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"No se pudo guardar el examen: {exc}")

        if goto_clicked:
            target = int(goto_question)
            target_page = _wizard_page_for_question(target)
            if target_page != current_page:
                _flush_question_page_to_drafts(start, end)
                st.session_state.exam_wizard_page = target_page
            st.session_state.wizard_focus_question = target
            st.rerun()


def page_exam_detail() -> None:
    if not st.session_state.teacher or not st.session_state.exam_id:
        st.session_state.page = "panel"
        st.rerun()
        return

    exam = None
    try:
        exam = get_exam(st.session_state.exam_id, st.session_state.teacher["id"])
    except Exception as exc:
        _render_db_error("cargar el examen", exc, retry_key="exam_detail_retry")
        return
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
    exam_points = question_total_points(exam["questions"])
    scoring_label = (
        "1 pt por pregunta"
        if (exam.get("scoring_mode") or "equal") == "equal"
        else "puntaje manual"
    )
    schedule = format_exam_schedule(exam.get("exam_date"), exam.get("exam_time"))
    pass_note = ""
    if exam.get("pass_min_score") is not None:
        pass_note = f" · Aprueba con {format_score(float(exam['pass_min_score']))}+"
    st.caption(
        f"{exam.get('career') or ''} · {exam.get('subject') or ''} · "
        f"{('Año ' + exam['career_year']) if exam.get('career_year') else ''} · "
        f"{schedule + ' · ' if schedule else ''}"
        f"{len(exam['questions'])} preguntas · {format_score(exam_points)} pts totales · "
        f"{scoring_label} · Nota 0-{exam['max_score']}{pass_note}"
    )
    if exam.get("description"):
        st.info(exam["description"])

    if st.session_state.pop("flash_download_exam", False):
        st.success(
            "Examen guardado en EvaluAR. **Descargalo ahora** y guardalo en tu computadora "
            "para no perder la clave de respuestas."
        )

    st.markdown("### Respaldo en tu computadora")
    st.caption(
        "Descargá este archivo `.json` y guardalo en tu disco. Contiene el examen completo "
        "y la clave de respuestas. Podés restaurarlo desde el panel docente si hace falta."
    )
    _render_exam_backup_download(exam, label="Descargar examen y clave (.json)")

    with st.expander("¿Cómo funciona el día del examen?", expanded=False):
        st.markdown(
            """
            **Antes del examen:** ya cargaste el examen y la clave de respuestas (al crear el examen).

            **El día del examen:**
            1. Generá el **código del examen** (botón de abajo) — **una sola vez** por comisión.
            2. Enviá a los alumnos la **URL de EvaluAR** + el **código** (WhatsApp).
            3. Rinden en **papel** en el aula; recogen los cuadernillos.
            4. Los alumnos entran a EvaluAR → **Soy alumno** → cargan sus respuestas con el código.
            5. Vos ves acá la **planilla de notas**, descargás Excel o CSV y **guardás el archivo en tu computadora**.
            6. Cuando la comisión terminó de cargar, **cerrá el código** (debajo del QR).

            El código **no es** para rendir online: es para **cargar respuestas después** del examen en papel.
            """
        )

    st.markdown("### Código del examen para alumnos")
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
                f"Hay **{len(sessions)} códigos** generados. Usá **uno solo** por examen. "
                "Podés **eliminar** los de prueba más abajo y dejar el definitivo."
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
            "Código activo de este examen",
            range(len(sessions)),
            format_func=lambda i: options[i],
            index=default_index,
            key="active_session_code_select",
        )
        active = sessions[selected_index]
        session_open = is_session_open(active)

        _render_metrics_row(
            [
                ("Código para alumnos", active["code"]),
                ("Respuestas cargadas", active["submission_count"]),
                ("Estado del código", "Abierto" if session_open else "Cerrado"),
                ("Nota máxima", format_score(float(exam["max_score"]))),
            ]
        )

        if st.button("Ver planilla de notas y descargar Excel", type="primary"):
            st.session_state.session_id = active["id"]
            st.session_state.page = "session_results"
            st.rerun()

        st.markdown("**Enviar a la comisión (después de rendir en papel)**")
        _render_session_share(active["code"], "active_session")

        st.divider()
        _render_session_access_control(active, st.session_state.teacher["id"])
        st.divider()
        _render_session_delete(active, st.session_state.teacher["id"])

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

    try:
        data = get_session_results(st.session_state.session_id, st.session_state.teacher["id"])
    except Exception as exc:
        _render_db_error("cargar los resultados de la sesión", exc, retry_key="session_results_retry")
        return
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
    exam_points = question_total_points(data["questions"])
    pass_min = (
        float(exam["pass_min_score"])
        if exam.get("pass_min_score") is not None
        else None
    )
    pass_caption = (
        f" · Aprueba con {format_score(pass_min)}+"
        if pass_min is not None
        else ""
    )
    st.caption(
        f"{exam.get('career') or ''} · {exam.get('subject') or ''} · "
        f"{exam['title']} · Sesión {session['code']} · "
        f"{format_score(exam_points)} pts totales · Nota 0-{exam['max_score']}{pass_caption}"
    )

    avg = 0 if not submissions else sum(s["score"] for s in submissions) / len(submissions)
    if pass_min is not None and submissions:
        approved = sum(1 for s in submissions if float(s["score"]) >= pass_min)
        _render_metrics_row(
            [
                ("Alumnos evaluados", len(submissions)),
                ("Aprobados", approved),
                ("Promedio", format_grade(avg)),
                ("Nota mínima", format_grade(pass_min)),
            ]
        )
    else:
        _render_metrics_row(
            [
                ("Alumnos evaluados", len(submissions)),
                ("Promedio", format_grade(avg)),
                ("Nota máxima", format_score(float(exam["max_score"]))),
            ]
        )

    if submissions:
        df = _submissions_dataframe(submissions, float(exam["max_score"]), pass_min)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.warning(
            "**Guardá la planilla en tu computadora.** Descargá Excel o CSV y archivá el archivo "
            "en tu disco: es tu copia permanente de las notas de esta comisión."
        )

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
            "Todavía no hay respuestas. Compartí el link con los alumnos después del examen "
            f"en papel: `?code={session['code']}`"
        )

    st.markdown("### Estadísticas por pregunta")
    st.dataframe(
        _question_stats_dataframe(data["question_stats"]),
        use_container_width=True,
        hide_index=True,
    )


def page_student() -> None:
    raw_code = st.session_state.student_code or st.query_params.get("code", "")
    if isinstance(raw_code, list):
        raw_code = raw_code[0] if raw_code else ""
    code = str(raw_code or "").strip().upper()
    if not code:
        st.warning("Ingresá un código del examen desde la barra lateral.")
        return

    try:
        payload = _get_student_session_payload(code)
    except Exception as exc:
        st.error(
            "No se pudo conectar con el servidor. Esperá unos segundos y recargá la página. "
            "Si ya marcaste respuestas, no cierres la pestaña: se pueden conservar al reconectar."
        )
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        if st.button("Reintentar conexión", type="primary"):
            st.session_state.student_exam_payload = None
            st.rerun()
        return

    if not payload:
        st.error("Código no encontrado. Verificá que sea el correcto.")
        return

    session = payload["session"]
    exam = payload["exam"]
    questions = payload["questions"]

    st.subheader(exam["title"])
    exam_points = question_total_points(questions)
    parts = [
        exam.get("career"),
        exam.get("subject"),
        f"Año {exam['career_year']}" if exam.get("career_year") else None,
        session.get("label"),
        f"{format_score(exam_points)} pts totales",
        f"Nota 0-{exam['max_score']}",
    ]
    st.caption(" · ".join(part for part in parts if part))

    if not is_session_open(session):
        st.error("Esta sesión no está abierta para envíos.")
        return

    if st.session_state.student_result:
        result = st.session_state.student_result
        st.success("Respuestas enviadas correctamente.")
        _render_metric_card(
            "Tu nota",
            f"{format_grade(result['score'])} / {format_grade(result['max_score'])}",
        )
        pass_min = result.get("pass_min_score")
        status = passing_status(float(result["score"]), pass_min)
        if status is not None:
            if status == "Aprobado":
                st.success(f"Estado: **{status}** (nota mínima {format_score(float(pass_min))})")
            else:
                st.warning(f"Estado: **{status}** (nota mínima {format_score(float(pass_min))})")
        if result.get("earned_points") is not None and result.get("total_points") is not None:
            st.info(
                format_grading_summary(
                    float(result["earned_points"]),
                    float(result["total_points"]),
                    float(result["max_score"]),
                    float(result["score"]),
                )
            )
        _render_metrics_row(
            [
                ("Aciertos", result["correct_count"]),
                ("Errores", result["wrong_count"]),
                ("Sin responder", result["unanswered_count"]),
            ]
        )
        if result.get("show_detail", True):
            incorrect_nums = result.get("incorrect_questions")
            unanswered_nums = result.get("unanswered_questions")
            if incorrect_nums is None and unanswered_nums is None:
                combined = result.get("wrong_questions") or []
                if combined:
                    st.warning(
                        "Preguntas incorrectas u omitidas: **"
                        + ", ".join(map(str, combined))
                        + "**"
                    )
            else:
                if incorrect_nums:
                    st.error(
                        "Preguntas respondidas mal: **"
                        + ", ".join(map(str, incorrect_nums))
                        + "**"
                    )
                if unanswered_nums:
                    st.warning(
                        "Preguntas sin responder: **"
                        + ", ".join(map(str, unanswered_nums))
                        + "**"
                    )
                if not incorrect_nums and not unanswered_nums:
                    st.success("Todas las preguntas respondidas correctamente.")
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
                st.session_state.student_page_num = 1
                st.session_state.student_exam_payload = None
                st.session_state.student_answer_code = None
                _clear_student_answer_widgets()
                st.rerun()
        return

    st.markdown("Marcá la opción que elegiste en tu cuadernillo de papel.")
    _sync_student_answer_state(code)
    page_size = 10
    total_pages = max(1, (len(questions) + page_size - 1) // page_size)
    current_page = int(st.session_state.get("student_page_num", 1))
    current_page = max(1, min(current_page, total_pages))
    st.session_state.student_page_num = current_page
    start_idx = (current_page - 1) * page_size
    visible = questions[start_idx : start_idx + page_size]
    first_q = visible[0]["order"] if visible else 1
    last_q = visible[-1]["order"] if visible else len(questions)

    st.info(
        f"Página **{current_page}** de **{total_pages}** · "
        f"Preguntas **{first_q}** a **{last_q}** de **{len(questions)}**"
    )

    nav_prev, nav_next = st.columns(2)
    with nav_prev:
        if current_page > 1 and st.button("← Página anterior", use_container_width=True):
            _flush_student_page_answers(visible)
            st.session_state.student_page_num = current_page - 1
            st.rerun()
    with nav_next:
        if current_page < total_pages and st.button(
            "Página siguiente →", use_container_width=True, type="primary"
        ):
            _flush_student_page_answers(visible)
            st.session_state.student_page_num = current_page + 1
            st.rerun()

    for question in visible:
        _render_student_question(question)

    st.divider()
    nav_prev2, nav_next2, nav_send = st.columns([1, 1, 1])
    with nav_prev2:
        if current_page > 1 and st.button(
            "← Anterior", use_container_width=True, key="student_prev_bottom"
        ):
            _flush_student_page_answers(visible)
            st.session_state.student_page_num = current_page - 1
            st.rerun()
    with nav_next2:
        if current_page < total_pages and st.button(
            "Siguiente →",
            use_container_width=True,
            type="primary",
            key="student_next_bottom",
        ):
            _flush_student_page_answers(visible)
            st.session_state.student_page_num = current_page + 1
            st.rerun()
    with nav_send:
        if current_page == total_pages and st.button(
            "Enviar respuestas", type="primary", use_container_width=True
        ):
            answers = _collect_student_answers(questions, visible)
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
            except Exception:
                st.error(
                    "No se pudieron enviar las respuestas. La conexión puede estar reconectando. "
                    "Esperá unos segundos y volvé a tocar **Enviar respuestas** (tus respuestas "
                    "siguen en pantalla)."
                )


def main() -> None:
    _bootstrap_db()
    ensure_state()

    code_param = st.query_params.get("code")
    if code_param:
        if isinstance(code_param, list):
            code_param = code_param[0] if code_param else ""
        if code_param:
            st.session_state.student_code = str(code_param).upper()
            st.session_state.page = "student"

    _inject_brand_theme()
    render_header()
    render_sidebar()

    page = st.session_state.page
    try:
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
    except Exception as exc:
        _render_db_error("completar esta acción", exc, retry_key="main_retry")


if __name__ == "__main__":
    main()
