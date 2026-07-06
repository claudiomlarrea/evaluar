#!/usr/bin/env python3
"""Genera el flyer PDF del webinar EvaluAR con enlace clicable a Google Meet."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "logo-observatorio-ia.png"
OUTPUT = ROOT / "assets" / "flyer-webinar-evaluar-16julio-2026.pdf"

RED = colors.HexColor("#7a1532")
RED_DARK = colors.HexColor("#4a0c1f")
YELLOW = colors.HexColor("#F4B400")
GREEN = colors.HexColor("#064a38")
GREEN_MID = colors.HexColor("#0d6e4f")
WHITE = colors.white
TEXT = colors.HexColor("#1f1418")
TEXT_SOFT = colors.HexColor("#5c4f54")

MEET_URL = "https://meet.google.com/aid-icaq-wjz"


class FlyerCanvas(canvas.Canvas):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._saved_page_states = []

  def showPage(self):
    self._saved_page_states.append(dict(self.__dict__))
    self._startPage()

  def save(self):
    num_pages = len(self._saved_page_states)
    for state in self._saved_page_states:
      self.__dict__.update(state)
      self.draw_page_background()
      super().showPage()
    super().save()

  def draw_page_background(self):
    w, h = A4
    self.setFillColor(RED_DARK)
    self.rect(0, h - 95 * mm, w, 95 * mm, fill=1, stroke=0)
    self.setFillColor(YELLOW)
    self.rect(0, h - 112 * mm, w, 17 * mm, fill=1, stroke=0)
    self.setFillColor(GREEN)
    self.rect(0, 0, w, 32 * mm, fill=1, stroke=0)


def build_pdf() -> None:
  doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=18 * mm,
    topMargin=14 * mm,
    bottomMargin=36 * mm,
  )

  styles = getSampleStyleSheet()
  title = ParagraphStyle(
    "Title",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=26,
    textColor=WHITE,
    alignment=TA_CENTER,
    spaceAfter=2,
  )
  subtitle = ParagraphStyle(
    "Subtitle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=11,
    textColor=WHITE,
    alignment=TA_CENTER,
    spaceAfter=4,
  )
  kicker = ParagraphStyle(
    "Kicker",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=WHITE,
    alignment=TA_CENTER,
    spaceAfter=2,
    leading=11,
  )
  date_style = ParagraphStyle(
    "Date",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=13,
    textColor=TEXT,
    alignment=TA_CENTER,
    leading=16,
  )
  body = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=11.5,
    textColor=TEXT,
    alignment=TA_LEFT,
    leading=16,
    spaceAfter=6,
  )
  question = ParagraphStyle(
    "Question",
    parent=body,
    fontName="Helvetica-Bold",
    fontSize=13,
    spaceAfter=10,
  )
  speaker = ParagraphStyle(
    "Speaker",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=12,
    textColor=WHITE,
    alignment=TA_CENTER,
    leading=15,
  )
  footer_title = ParagraphStyle(
    "FooterTitle",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=11,
    textColor=WHITE,
    alignment=TA_CENTER,
    leading=13,
  )
  footer_link = ParagraphStyle(
    "FooterLink",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=12,
    textColor=WHITE,
    alignment=TA_CENTER,
    leading=14,
  )
  footer_note = ParagraphStyle(
    "FooterNote",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    textColor=WHITE,
    alignment=TA_CENTER,
    leading=11,
  )

  logo_w = 42 * mm
  logo = Table(
    [[Paragraph(
      f'<img src="{LOGO}" width="{logo_w}" height="{logo_w}"/>',
      ParagraphStyle("img", alignment=TA_CENTER),
    )]],
    colWidths=[doc.width],
  )

  story = [
    logo,
    Spacer(1, 4 * mm),
    Paragraph("UNIVERSIDAD CATÓLICA DE CUYO", kicker),
    Paragraph("Observatorio de Inteligencia Artificial", subtitle),
    Spacer(1, 3 * mm),
    Paragraph("WEBINAR", kicker),
    Paragraph("EvaluAR", title),
    Paragraph("Examen en papel · Corrección digital", subtitle),
    Spacer(1, 22 * mm),
    Paragraph("Jueves 16 de julio · 18:00 – 19:00 hs", date_style),
    Spacer(1, 10 * mm),
    Paragraph(
      "¿Cómo evaluar parciales presenciales con cientos de alumnos en minutos?",
      question,
    ),
    Paragraph("• Los alumnos rinden en papel y cargan respuestas desde el celular", body),
    Paragraph("• El docente configura la clave y el sistema corrige al instante", body),
    Paragraph("• Planilla de notas y exportación a Excel", body),
    Paragraph(
      "Dirigido a <b>docentes, investigadores y demás interesados</b>.",
      body,
    ),
    Spacer(1, 6 * mm),
  ]

  speaker_box = Table(
    [[Paragraph("Disertante: Dr. Claudio Marcelo Larrea", speaker)]],
    colWidths=[doc.width],
  )
  speaker_box.setStyle(
    TableStyle(
      [
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_MID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
      ]
    )
  )
  story.append(speaker_box)
  story.append(Spacer(1, 28 * mm))

  footer = Table(
    [
      [Paragraph("Google Meet · EvaluAR", footer_title)],
      [
        Paragraph(
          f'<a href="{MEET_URL}" color="white">meet.google.com/aid-icaq-wjz</a>',
          footer_link,
        )
      ],
      [Paragraph("Inscripción gratuita · Cupo abierto", footer_note)],
    ],
    colWidths=[doc.width],
  )
  footer.setStyle(
    TableStyle(
      [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
      ]
    )
  )
  story.append(footer)

  doc.build(story, canvasmaker=FlyerCanvas)
  print(f"PDF generado: {OUTPUT}")


if __name__ == "__main__":
  if not LOGO.is_file():
    raise SystemExit(f"No se encontró el logo: {LOGO}")
  build_pdf()
