#!/usr/bin/env python3
"""Genera el flyer PDF compacto del webinar EvaluAR."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "logo-observatorio-ia.png"
OUTPUT = ROOT / "assets" / "flyer-webinar-evaluar-16julio-2026.pdf"
DOCS_OUTPUT = Path.home() / "Documents" / "EvaluAR" / "flyer-webinar-evaluar-16julio-2026.pdf"

# Formato compacto (no A4): ~12 × 18,8 cm
PAGE_SIZE = (120 * mm, 188 * mm)

RED_DARK = colors.HexColor("#4a0c1f")
YELLOW = colors.HexColor("#F4B400")
GREEN = colors.HexColor("#064a38")
GREEN_MID = colors.HexColor("#0d6e4f")
WHITE = colors.white
TEXT = colors.HexColor("#1f1418")

MEET_URL = "https://meet.google.com/aid-icaq-wjz"
MEET_LABEL = "meet.google.com/aid-icaq-wjz"
FORM_URL = (
    "https://docs.google.com/forms/d/e/1FAIpQLSciYdyCaC2gAZRXzUtiDZ2asV5R3KIX2kUguyi_frNpe3VKEA/"
    "viewform?usp=sharing&ouid=102865527515262890038"
)
FORM_LABEL = "Inscribite aquí · Google Forms"


def _centered_link(
    c: canvas.Canvas,
    page_w: float,
    text: str,
    url: str,
    y: float,
    font: str,
    size: float,
) -> None:
    width = c.stringWidth(text, font, size)
    x = (page_w - width) / 2
    c.setFont(font, size)
    c.drawString(x, y, text)
    c.linkURL(url, (x, y - 1, x + width, y + size + 2), relative=0)


def _wrap_lines(text: str, max_width: float, c: canvas.Canvas, font: str, size: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if c.stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_round_logo(c: canvas.Canvas, path: Path, cx: float, cy: float, diameter: float) -> None:
    radius = diameter / 2
    c.saveState()
    clip = c.beginPath()
    clip.circle(cx, cy, radius)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(
        ImageReader(str(path)),
        cx - radius,
        cy - radius,
        diameter,
        diameter,
        mask="auto",
    )
    c.restoreState()
    c.setStrokeColor(WHITE)
    c.setLineWidth(1.2)
    c.circle(cx, cy, radius, stroke=1, fill=0)


def _draw_lines(
    c: canvas.Canvas,
    x: float,
    y: float,
    lines: list[str],
    font: str,
    size: float,
    leading: float,
) -> float:
    c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_pdf(output: Path = OUTPUT) -> Path:
    w, h = PAGE_SIZE
    margin = 9 * mm
    content_w = w - 2 * margin

    header_h = 68 * mm
    date_h = 10 * mm
    footer_h = 34 * mm

    c = canvas.Canvas(str(output), pagesize=PAGE_SIZE)

    c.setFillColor(RED_DARK)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    c.rect(0, h - header_h - date_h, w, date_h, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, 0, w, footer_h, fill=1, stroke=0)

    logo_d = 24 * mm
    logo_cy = h - 15 * mm
    _draw_round_logo(c, LOGO, w / 2, logo_cy, logo_d)

    c.setFillColor(WHITE)
    y = logo_cy - logo_d / 2 - 4 * mm
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(w / 2, y, "UNIVERSIDAD CATÓLICA DE CUYO")
    y -= 4.5 * mm
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(w / 2, y, "Observatorio de Inteligencia Artificial")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(w / 2, y, "WEBINAR")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, y, "EvaluAR")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, y, "Examen en papel · Corrección digital")

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, h - header_h - date_h + 3.2 * mm, "Jueves 16 de julio · 18:00 – 19:00 hs")

    y = h - header_h - date_h - 7 * mm
    c.setFillColor(TEXT)
    question = "¿Cómo evaluar exámenes presenciales con cientos de alumnos en minutos?"
    y = _draw_lines(
        c,
        margin,
        y,
        _wrap_lines(question, content_w, c, "Helvetica-Bold", 10.5),
        "Helvetica-Bold",
        10.5,
        12,
    )

    y -= 2 * mm
    bullets = [
        "• Los alumnos rinden en papel y cargan respuestas desde el celular",
        "• El docente configura la clave y el sistema corrige al instante",
        "• Planilla de notas y exportación a Excel",
    ]
    for bullet in bullets:
        y = _draw_lines(
            c,
            margin,
            y,
            _wrap_lines(bullet, content_w - 2 * mm, c, "Helvetica", 9.5),
            "Helvetica",
            9.5,
            11,
        )
        y -= 1 * mm

    y -= 2 * mm
    y = _draw_lines(
        c,
        margin,
        y,
        _wrap_lines(
            "Dirigido a docentes, investigadores y demás interesados.",
            content_w,
            c,
            "Helvetica-Bold",
            9.5,
        ),
        "Helvetica-Bold",
        9.5,
        11,
    )

    y -= 4 * mm
    box_h = 11 * mm
    speaker_y = y - box_h
    c.setFillColor(GREEN_MID)
    c.roundRect(margin, speaker_y, content_w, box_h, 4, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(w / 2, speaker_y + 3.2 * mm, "Disertante: Dr. Claudio Marcelo Larrea")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w / 2, 26 * mm, "Inscripción gratuita · Cupo abierto")
    _centered_link(c, w, FORM_LABEL, FORM_URL, 19 * mm, "Helvetica-Bold", 9)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(w / 2, 13 * mm, "Webinar por Google Meet")
    _centered_link(c, w, MEET_LABEL, MEET_URL, 6.5 * mm, "Helvetica-Bold", 8.5)

    c.save()
    return output


if __name__ == "__main__":
    if not LOGO.is_file():
        raise SystemExit(f"No se encontró el logo: {LOGO}")
    path = build_pdf()
    print(f"PDF generado: {path}")
    DOCS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(DOCS_OUTPUT)
    print(f"Copiado a: {DOCS_OUTPUT}")
