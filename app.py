"""Punto de entrada para Streamlit Cloud."""

from __future__ import annotations

import streamlit as st


def _show_boot_error(exc: BaseException, *, configure_page: bool) -> None:
    if configure_page:
        try:
            st.set_page_config(page_title="EvaluAR", layout="wide")
        except Exception:
            pass
    st.error("EvaluAR no pudo iniciar. Probá recargar en unos segundos.")
    with st.expander("Detalle técnico (para soporte)"):
        st.exception(exc)


try:
    from streamlit_app import main
except Exception as exc:  # noqa: BLE001 — mostrar fallo de import en Cloud
    _show_boot_error(exc, configure_page=True)
else:
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — no ocultar crash detrás de "Oh no"
        _show_boot_error(exc, configure_page=False)
