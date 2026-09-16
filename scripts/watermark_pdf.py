"""Stamp a firm name onto every page of a PDF before it goes into that
firm's data room. Each firm gets its own watermarked copy -- never the same
file shared across firms.
"""

import io
import pathlib

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _watermark_overlay(page_width, page_height, text):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.saveState()
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(0.6, 0.6, 0.6, alpha=0.5)
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def watermark_pdf(input_path, output_path, firm_name):
    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    text = "CONFIDENTIAL -- Prepared for {} -- Do not distribute".format(firm_name)

    for page in reader.pages:
        overlay = _watermark_overlay(float(page.mediabox.width), float(page.mediabox.height), text)
        page.merge_page(overlay)
        writer.add_page(page)

    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    return str(output_path)
