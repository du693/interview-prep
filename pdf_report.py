import io
from datetime import datetime

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

BG = HexColor("#14161b")
SURFACE_2 = HexColor("#232730")
BORDER = HexColor("#343a45")
TEXT = HexColor("#e7e9ee")
MUTED = HexColor("#8d93a0")
FAINT = HexColor("#5f6571")
ACCENT = HexColor("#5b7fff")
ACCENT_SOFT = HexColor("#202a45")
GLOW = HexColor("#d9a441")

MARGIN = 40
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _sanitize(text: str) -> str:
    return (text or "").replace("→", "->")


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = _sanitize(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _ellipsize(line: str, font: str, size: float, max_width: float) -> str:
    while line and stringWidth(line + "…", font, size) > max_width:
        line = line[:-1].rstrip()
    return line + "…"


def _icon_chip(c: canvas.Canvas, x: float, y: float, size: float):
    c.setFillColor(ACCENT_SOFT)
    c.roundRect(x, y, size, size, size * 0.3, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.circle(x + size / 2, y + size / 2, size * 0.15, fill=1, stroke=0)


def _brand_mark(c: canvas.Canvas, x: float, y: float, size: float):
    c.setFillColor(ACCENT_SOFT)
    c.roundRect(x, y, size, size, size * 0.26, fill=1, stroke=0)
    cx, cy = x + size / 2, y + size / 2
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.4)
    c.circle(cx, cy, size * 0.22, fill=0, stroke=1)
    c.setFillColor(ACCENT)
    c.circle(cx, cy, size * 0.055, fill=1, stroke=0)


def _badge(c: canvas.Canvas, cx: float, cy: float, r: float, number: int):
    c.setFillColor(ACCENT_SOFT)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.setFont(FONT_BOLD, 7.5)
    label = str(number)
    tw = stringWidth(label, FONT_BOLD, 7.5)
    c.drawString(cx - tw / 2, cy - 2.6, label)


def _draw_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, body: str):
    c.setFillColor(SURFACE_2)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, 9, fill=1, stroke=1)

    c.setFillColor(ACCENT)
    c.roundRect(x, y + 8, 2.4, h - 16, 1.2, fill=1, stroke=0)

    pad = 16
    chip = 13
    chip_y = y + h - pad - chip + 1
    _icon_chip(c, x + pad, chip_y, chip)

    c.setFillColor(ACCENT)
    c.setFont(FONT_BOLD, 7.6)
    c.drawString(x + pad + chip + 8, y + h - pad - 1, title.upper())

    body_font, body_size, leading = FONT, 8.4, 11.5
    max_width = w - 2 * pad
    lines = _wrap(body, body_font, body_size, max_width)
    top_offset = pad + chip + 10
    max_lines = max(1, int((h - top_offset - 10) // leading))

    shown = lines[:max_lines]
    if len(lines) > max_lines and shown:
        shown[-1] = _ellipsize(shown[-1], body_font, body_size, max_width)

    c.setFillColor(TEXT)
    c.setFont(body_font, body_size)
    ty = y + h - top_offset
    for line in shown:
        c.drawString(x + pad, ty, line)
        ty -= leading


def _draw_questions_card(
    c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, questions: list[str]
):
    c.setFillColor(SURFACE_2)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, 9, fill=1, stroke=1)

    c.setFillColor(ACCENT)
    c.roundRect(x, y + 8, 2.4, h - 16, 1.2, fill=1, stroke=0)

    pad = 16
    chip = 13
    chip_y = y + h - pad - chip + 1
    _icon_chip(c, x + pad, chip_y, chip)

    c.setFillColor(ACCENT)
    c.setFont(FONT_BOLD, 7.6)
    title_max_w = w - pad - chip - 8 - pad
    title_text = title.upper()
    if stringWidth(title_text, FONT_BOLD, 7.6) > title_max_w:
        title_text = _ellipsize(title_text, FONT_BOLD, 7.6, title_max_w)
    c.drawString(x + pad + chip + 8, y + h - pad - 1, title_text)

    body_font, body_size, leading = FONT, 8.2, 11
    badge_r = 7
    text_x = x + pad + badge_r * 2 + 9
    max_width = w - pad - (badge_r * 2 + 9) - pad
    ty = y + h - pad - chip - 16

    for i, question in enumerate(questions[:3], start=1):
        lines = _wrap(question, body_font, body_size, max_width)[:3]
        _badge(c, x + pad + badge_r, ty + 2, badge_r, i)
        c.setFillColor(TEXT)
        c.setFont(body_font, body_size)
        for j, line in enumerate(lines):
            c.drawString(text_x, ty - j * leading, line)
        ty -= leading * max(1, len(lines)) + 11


def generate_pdf(company_name: str, job_title: str, result: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    c.setFillColor(BG)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    mark_size = 30
    mark_x, mark_y = MARGIN, height - MARGIN - mark_size + 4
    _brand_mark(c, mark_x, mark_y, mark_size)

    text_x = mark_x + mark_size + 12
    max_title_w = width - MARGIN - text_x
    title = _sanitize(f"{company_name} — {job_title}")
    if stringWidth(title, FONT_BOLD, 17) > max_title_w:
        title = _ellipsize(title, FONT_BOLD, 17, max_title_w)
    c.setFillColor(TEXT)
    c.setFont(FONT_BOLD, 17)
    c.drawString(text_x, height - MARGIN - 12, title)

    sub_y = height - MARGIN - 26
    c.setFillColor(MUTED)
    c.setFont(FONT, 8.5)
    label = "Interview Briefing"
    c.drawString(text_x, sub_y, label)
    dot_x = text_x + stringWidth(label, FONT, 8.5) + 8
    c.setFillColor(GLOW)
    c.circle(dot_x, sub_y + 3, 2, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.drawString(dot_x + 8, sub_y, f"Generated {datetime.now().strftime('%b %d, %Y')}")

    divider_y = height - MARGIN - mark_size - 2
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.line(MARGIN, divider_y, width - MARGIN, divider_y)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(MARGIN, divider_y, MARGIN + 36, divider_y)

    grid_top = divider_y - 22
    col_w = (width - 2 * MARGIN - 16) / 2
    row_h = 100
    gap = 16

    cards = [
        ("What they're looking for", result.get("candidate_profile", "")),
        ("Culture", result.get("culture", "")),
        ("Experience level", result.get("experience_level", "")),
        ("Environment", result.get("environment", "")),
        ("The company", result.get("company_explainer", "")),
        ("Locations", result.get("locations", "")),
    ]

    last_row_bottom = grid_top
    for i, (title_text, body) in enumerate(cards):
        col, row = i % 2, i // 2
        x = MARGIN + col * (col_w + 16)
        y = grid_top - row_h - row * (row_h + gap)
        _draw_card(c, x, y, col_w, row_h, title_text, body)
        last_row_bottom = min(last_row_bottom, y)

    q_height = 200
    q_y = last_row_bottom - gap - q_height
    _draw_questions_card(
        c, MARGIN, q_y, col_w, q_height, "Questions to ask", result.get("role_questions", [])
    )
    _draw_questions_card(
        c,
        MARGIN + col_w + 16,
        q_y,
        col_w,
        q_height,
        "From your research",
        result.get("research_questions", []),
    )

    footer_line_y = q_y - 18
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(MARGIN, footer_line_y, MARGIN + 36, footer_line_y)
    c.setFillColor(FAINT)
    c.setFont(FONT, 7.2)
    c.drawString(MARGIN, footer_line_y - 13, "Research, read, write — walk in ready.  ·  Generated by Interview Prep")

    c.showPage()
    c.save()
    return buf.getvalue()
