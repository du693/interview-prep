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


def _card_frame(c: canvas.Canvas, x: float, y: float, w: float, h: float):
    c.setFillColor(SURFACE_2)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, 9, fill=1, stroke=1)
    c.setFillColor(ACCENT)
    c.roundRect(x, y + 8, 2.4, h - 16, 1.2, fill=1, stroke=0)


def _card_title(c: canvas.Canvas, x: float, y: float, w: float, title: str, chip: float, pad: float):
    chip_y = y - chip + 1
    _icon_chip(c, x, chip_y, chip)
    c.setFillColor(ACCENT)
    c.setFont(FONT_BOLD, 7.6)
    title_max_w = w - chip - 8
    title_text = title.upper()
    if stringWidth(title_text, FONT_BOLD, 7.6) > title_max_w:
        title_text = _ellipsize(title_text, FONT_BOLD, 7.6, title_max_w)
    c.drawString(x + chip + 8, y - 1, title_text)


def _draw_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, body: str):
    _card_frame(c, x, y, w, h)

    pad = 16
    chip = 13
    _card_title(c, x + pad, y + h - pad, w - 2 * pad, title, chip, pad)

    body_font, body_size, leading = FONT, 8.3, 11
    max_width = w - 2 * pad
    lines = _wrap(body, body_font, body_size, max_width)
    top_offset = pad + chip + 9
    max_lines = max(1, int((h - top_offset - 8) // leading))

    shown = lines[:max_lines]
    if len(lines) > max_lines and shown:
        shown[-1] = _ellipsize(shown[-1], body_font, body_size, max_width)

    c.setFillColor(TEXT)
    c.setFont(body_font, body_size)
    ty = y + h - top_offset
    for line in shown:
        c.drawString(x + pad, ty, line)
        ty -= leading


def _draw_list_card(
    c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, items: list[str], max_items: int
):
    _card_frame(c, x, y, w, h)

    pad = 16
    chip = 13
    _card_title(c, x + pad, y + h - pad, w - 2 * pad, title, chip, pad)

    body_font, body_size, leading = FONT, 8.2, 10.8
    badge_r = 7
    text_x = x + pad + badge_r * 2 + 9
    max_width = w - pad - (badge_r * 2 + 9) - pad
    ty = y + h - pad - chip - 14

    for i, item in enumerate(items[:max_items], start=1):
        all_lines = _wrap(item, body_font, body_size, max_width)
        lines = all_lines[:3]
        if len(all_lines) > 3 and lines:
            lines[-1] = _ellipsize(lines[-1], body_font, body_size, max_width)
        _badge(c, x + pad + badge_r, ty + 2, badge_r, i)
        c.setFillColor(TEXT)
        c.setFont(body_font, body_size)
        for j, line in enumerate(lines):
            c.drawString(text_x, ty - j * leading, line)
        ty -= leading * max(1, len(lines)) + 9


def generate_pdf(company_name: str, job_title: str, result: dict, stage_type: str = "intro_call") -> bytes:
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

    # --- assemble the dynamic card set ---
    text_cards = [
        ("What they're looking for", result.get("candidate_profile", "")),
        ("Culture", result.get("culture", "")),
        ("Experience level", result.get("experience_level", "")),
        ("Environment", result.get("environment", "")),
        ("The company", result.get("company_explainer", "")),
        ("Locations", result.get("locations", "")),
    ]
    if result.get("stage_brief"):
        text_cards.append(("What to expect", result["stage_brief"]))
    if result.get("watch_out"):
        text_cards.append(("Watch out for", result["watch_out"]))

    list_cards = []
    if result.get("skills_at_risk"):
        list_cards.append(("Skills at risk", result["skills_at_risk"], 3))
    if result.get("prep_plan"):
        list_cards.append(("Prep plan", result["prep_plan"], 4))

    role_questions = result.get("role_questions", [])
    research_questions = result.get("research_questions", [])

    # --- compute layout budget so everything fits one page ---
    col_w = (width - 2 * MARGIN - 16) / 2
    gap = 14
    grid_top = divider_y - 20
    bottom_reserve = 56  # footer rule + text + page margin

    list_row_h = 132 if list_cards else 0
    q_row_h = 122

    rows_needed = (len(text_cards) + 1) // 2
    available_for_grid = grid_top - bottom_reserve - q_row_h - gap - (list_row_h + gap if list_cards else 0)
    row_h = available_for_grid / rows_needed - gap * (rows_needed - 1) / rows_needed
    row_h = max(58, min(100, row_h))

    last_bottom = grid_top
    for i, (title_text, body) in enumerate(text_cards):
        col, row = i % 2, i // 2
        x = MARGIN + col * (col_w + 16)
        y = grid_top - row_h - row * (row_h + gap)
        _draw_card(c, x, y, col_w, row_h, title_text, body)
        last_bottom = min(last_bottom, y)

    if list_cards:
        list_y = last_bottom - gap - list_row_h
        if len(list_cards) == 1:
            title_text, items, max_items = list_cards[0]
            _draw_list_card(c, MARGIN, list_y, width - 2 * MARGIN, list_row_h, title_text, items, max_items)
        else:
            for i, (title_text, items, max_items) in enumerate(list_cards[:2]):
                x = MARGIN + i * (col_w + 16)
                _draw_list_card(c, x, list_y, col_w, list_row_h, title_text, items, max_items)
        last_bottom = list_y

    q_y = last_bottom - gap - q_row_h
    _draw_list_card(c, MARGIN, q_y, col_w, q_row_h, "Questions to ask", role_questions, 3)
    _draw_list_card(
        c, MARGIN + col_w + 16, q_y, col_w, q_row_h, "From your research", research_questions, 3
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
