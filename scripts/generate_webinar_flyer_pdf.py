#!/usr/bin/env python3
"""Genera el flyer PDF del webinar EvaluAR con enlace clicable a Google Meet."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "logo-observatorio-ia.png"
OUTPUT = ROOT / "assets" / "flyer-webinar-evaluar-16julio-2026.pdf"
DOCS_OUTPUT = Path.home() / "Documents" / "EvaluAR" / "flyer-webinar-evaluar-16julio-2026.pdf"

RED_DARK = colors.HexColor("#4a0c1f")
RED = colors.HexColor("#7a1532")
YELLOW = colors.HexColor("#F4B400")
GREEN = colors.HexColor("#064a38")
GREEN_MID = colors.HexColor("#0d6e4f")
WHITE = colors.white
TEXT = colors.HexColor("#1f1418")

MEET_URL = "https://meet.google.com/aid-icaq-wjz"
MEET_LABEL = "meet.google.com/aid-icaq-wjz"


def _centered_link(c: canvas.Canvas, text: str, url: str, y: float, font: str, size: float) -> None:
    width = c.stringWidth(text, font, size)
    x = (A4[0] - width) / 2
    c.setFont(font, size)
    c.drawString(x, y, text)
    c.linkURL(url, (x, y - 2, x + width, y + size + 2), relative=0)


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


def build_pdf(output: Path = OUTPUT) -> Path:
    w, h = A4
    margin = 18 * mm
    content_w = w - 2 * margin

    header_h = 98 * mm
    date_h = 16 * mm
    footer_h = 38 * mm

    c = canvas.Canvas(str(output), pagesize=A4)

    # Bandas de fondo (debajo del texto)
    c.setFillColor(RED_DARK)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    c.rect(0, h - header_h - date_h, w, date_h, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, 0, w, footer_h, fill=1, stroke=0)

    # Logo
    logo_size = 36 * mm
    logo_y = h - header_h + 42 * mm
    c.drawImage(
        ImageReader(str(LOGO)),
        (w - logo_size) / 2,
        logo_y,
        logo_size,
        logo_size,
        mask="auto",
    )

    # Encabezado
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(w / 2, logo_y - 5 * mm, "UNIVERSIDAD CATÓLICA DE CUYO")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, logo_y - 10 * mm, "Observatorio de Inteligencia Artificial")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w / 2, logo_y - 18 * mm, "WEBINAR")
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, logo_y - 30 * mm, "EvaluAR")
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, logo_y - 37 * mm, "Examen en papel · Corrección digital")

    # Fecha
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 13)
    date_y = h - header_h - date_h + 5 * mm
    c.drawCentredString(w / 2, date_y, "Jueves 16 de julio · 18:00 – 19:00 hs")

    # Cuerpo
    body_top = h - header_h - date_h - 12 * mm
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 13)
    question = "¿Cómo evaluar parciales presenciales con cientos de alumnos en minutos?"
    y = body_top
    for line in _wrap_lines(question, content_w, c, "Helvetica-Bold", 13):
        c.drawString(margin, y, line)
        y -= 16

    y -= 4
    c.setFont("Helvetica", 11.5)
    bullets = [
        "• Los alumnos rinden en papel y cargan respuestas desde el celular",
        "• El docente configura la clave y el sistema corrige al instante",
        "• Planilla de notas y exportación a Excel",
    ]
    for bullet in bullets:
        for line in _wrap_lines(bullet, content_w - 4 * mm, c, "Helvetica", 11.5):
            c.drawString(margin + 2 * mm, y, line)
            y -= 15
        y -= 2

    y -= 2
    audience = "Dirigido a docentes, investigadores y demás interesados."
    c.setFont("Helvetica-Bold", 11.5)
    for line in _wrap_lines(audience, content_w, c, "Helvetica-Bold", 11.5):
        c.drawString(margin, y, line)
        y -= 15

    # Caja disertante
    speaker_y = y - 8 * mm
    box_h = 14 * mm
    box_w = content_w
    box_x = margin
    c.setFillColor(GREEN_MID)
    c.roundRect(box_x, speaker_y, box_w, box_h, 5, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(w / 2, speaker_y + 4.5 * mm, "Disertante: Dr. Claudio Marcelo Larrea")

    # Pie con enlace clicable
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, 24 * mm, "Google Meet · EvaluAR")
    _centered_link(c, MEET_LABEL, MEET_URL, 16 * mm, "Helvetica-Bold", 12)
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, 8 * mm, "Inscripción gratuita · Cupo abierto")

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
