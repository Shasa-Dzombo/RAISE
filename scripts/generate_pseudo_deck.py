"""Generate a one-page pseudo teaser PDF for Mazao Analytics (the fictional
test company) -- exists only so the data-room pipeline has something real
to upload/watermark/share/track without needing the founder's actual deck.

Usage: python scripts/generate_pseudo_deck.py <output_path>
"""

import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

LINES = [
    ("Mazao Analytics -- PSEUDO TEST DATA, not a real company", 14, True),
    ("", 10, False),
    ("Real-time crop pricing and buyer matching for smallholder farmers,", 11, False),
    ("delivered over SMS and a lightweight app.", 11, False),
    ("", 10, False),
    ("Stage: Seed  |  Raising: $1,500,000 USD via SAFE", 11, False),
    ("Live in: Kenya, Uganda  |  Targeting next: Tanzania, Rwanda", 11, False),
    ("ARR: $180,000 USD  |  Runway: 7 months  |  Headcount: 18", 11, False),
    ("", 10, False),
    ("This document is a placeholder generated for testing RAISE's data", 9, False),
    ("room pipeline. It contains no real company information.", 9, False),
]


def generate(output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    y = height - 1.2 * inch
    for text, size, bold in LINES:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(1 * inch, y, text)
        y -= size + 6
    c.save()
    return output_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "mazao_teaser_pseudo.pdf"
    generate(out)
    print("wrote", out)
