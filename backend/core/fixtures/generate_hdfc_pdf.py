"""
generate_hdfc_pdf_fixture.py
Creates a realistic HDFC Bank PDF statement fixture for testing.
Uses reportlab to generate a properly formatted PDF with table data
that pdfplumber can extract.
"""
import os
import sys

# Try reportlab first; fall back to fpdf2 if available
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    USE_REPORTLAB = True
except ImportError:
    USE_REPORTLAB = False

try:
    from fpdf import FPDF
    USE_FPDF = not USE_REPORTLAB
except ImportError:
    USE_FPDF = False


def generate_with_reportlab(output_path):
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header text identifying this as HDFC
    elements.append(Paragraph("HDFC Bank Limited", styles['Title']))
    elements.append(Paragraph("Statement of Account", styles['Normal']))
    elements.append(Paragraph("Account No: XXXX5678 | Branch: Mumbai Main", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Transaction table
    data = [
        ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        ["01/09/2026", "UPI-RAPIDO-rider@paytm-RIDE PAYMENT", "UPI901234567", "01/09/2026", "85.00", "", "24915.00"],
        ["03/09/2026", "UPI-PHONEPE-merchant@ybl-RECHARGE", "UPI901234568", "03/09/2026", "299.00", "", "24616.00"],
        ["07/09/2026", "NEFT-SBIN0001234-PRIYA SHARMA-TRANSFER", "NEFT456789", "07/09/2026", "", "5000.00", "29616.00"],
        ["12/09/2026", "UPI-BIGBASKET-grocery@axl-GROCERIES", "UPI901234569", "12/09/2026", "1542.50", "", "28073.50"],
        ["18/09/2026", "UPI-UBER-ride@icici-CAB BOOKING", "UPI901234570", "18/09/2026", "234.00", "", "27839.50"],
        ["22/09/2026", "UPI-BOOKMYSHOW-tickets@paytm-MOVIE", "UPI901234571", "22/09/2026", "450.00", "", "27389.50"],
        ["28/09/2026", "IMPS-AXIS0001234-ROHAN GUPTA-SPLIT RENT", "IMPS789012", "28/09/2026", "3500.00", "", "23889.50"],
    ]

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#004B87')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (4, 1), (6, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    doc.build(elements)
    print(f"Generated HDFC PDF fixture (reportlab): {output_path}")


def generate_with_fpdf(output_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'HDFC Bank Limited', ln=True, align='C')
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'Statement of Account', ln=True, align='C')
    pdf.cell(0, 8, 'Account No: XXXX5678 | Branch: Mumbai Main', ln=True, align='C')
    pdf.ln(10)

    headers = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    rows = [
        ["01/09/2026", "UPI-RAPIDO-rider@paytm-RIDE PAYMENT", "UPI901234567", "01/09/2026", "85.00", "", "24915.00"],
        ["03/09/2026", "UPI-PHONEPE-merchant@ybl-RECHARGE", "UPI901234568", "03/09/2026", "299.00", "", "24616.00"],
        ["07/09/2026", "NEFT-SBIN0001234-PRIYA SHARMA-TRANSFER", "NEFT456789", "07/09/2026", "", "5000.00", "29616.00"],
        ["12/09/2026", "UPI-BIGBASKET-grocery@axl-GROCERIES", "UPI901234569", "12/09/2026", "1542.50", "", "28073.50"],
        ["18/09/2026", "UPI-UBER-ride@icici-CAB BOOKING", "UPI901234570", "18/09/2026", "234.00", "", "27839.50"],
        ["22/09/2026", "UPI-BOOKMYSHOW-tickets@paytm-MOVIE", "UPI901234571", "22/09/2026", "450.00", "", "27389.50"],
        ["28/09/2026", "IMPS-AXIS0001234-ROHAN GUPTA-SPLIT RENT", "IMPS789012", "28/09/2026", "3500.00", "", "23889.50"],
    ]
    col_widths = [22, 62, 28, 22, 25, 22, 25]

    # Header row
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(0, 75, 135)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, fill=True, align='C')
    pdf.ln()

    # Data rows
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(0, 0, 0)
    for row in rows:
        for i, cell in enumerate(row):
            align = 'R' if i >= 4 else 'L'
            pdf.cell(col_widths[i], 6, cell, border=1, align=align)
        pdf.ln()

    pdf.output(output_path)
    print(f"Generated HDFC PDF fixture (fpdf2): {output_path}")


def generate_minimal_pdf(output_path):
    """Fallback: generate a minimal PDF manually using raw PDF syntax.
    This creates a simple PDF with text that pdfplumber can extract as a table."""

    # We'll create a simple text-based PDF that contains the HDFC identifiers
    # and a table rendered as text lines
    lines = [
        "HDFC Bank Limited",
        "Statement of Account",
        "Account No: XXXX5678",
        "",
        "Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance",
        "01/09/2026 | UPI-RAPIDO-rider@paytm-RIDE PAYMENT | UPI901234567 | 01/09/2026 | 85.00 |  | 24915.00",
        "03/09/2026 | UPI-PHONEPE-merchant@ybl-RECHARGE | UPI901234568 | 03/09/2026 | 299.00 |  | 24616.00",
        "07/09/2026 | NEFT-SBIN0001234-PRIYA SHARMA-TRANSFER | NEFT456789 | 07/09/2026 |  | 5000.00 | 29616.00",
        "12/09/2026 | UPI-BIGBASKET-grocery@axl-GROCERIES | UPI901234569 | 12/09/2026 | 1542.50 |  | 28073.50",
        "18/09/2026 | UPI-UBER-ride@icici-CAB BOOKING | UPI901234570 | 18/09/2026 | 234.00 |  | 27839.50",
        "22/09/2026 | UPI-BOOKMYSHOW-tickets@paytm-MOVIE | UPI901234571 | 22/09/2026 | 450.00 |  | 27389.50",
        "28/09/2026 | IMPS-AXIS0001234-ROHAN GUPTA-SPLIT RENT | IMPS789012 | 28/09/2026 | 3500.00 |  | 23889.50",
    ]
    text = "\n".join(lines)

    # Build raw PDF
    stream = text.encode('latin-1', errors='replace')
    stream_content = f"BT /F1 10 Tf 50 750 Td ({text.replace(chr(10), ') Tj T* (')}) Tj ET"
    stream_bytes = stream_content.encode('latin-1', errors='replace')

    objects = []

    # obj 1: catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    # obj 2: pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    # obj 3: page
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj")
    # obj 4: stream
    obj4 = b"4 0 obj\n<< /Length " + str(len(stream_bytes)).encode() + b" >>\nstream\n" + stream_bytes + b"\nendstream\nendobj"
    objects.append(obj4)
    # obj 5: font
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")

    pdf = b"%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj + b"\n"
    xref_offset = len(pdf)
    pdf += b"xref\n"
    pdf += f"0 {len(objects)+1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += b"trailer\n"
    pdf += f"<< /Size {len(objects)+1} /Root 1 0 R >>\n".encode()
    pdf += b"startxref\n"
    pdf += f"{xref_offset}\n".encode()
    pdf += b"%%EOF\n"

    with open(output_path, 'wb') as f:
        f.write(pdf)
    print(f"Generated HDFC PDF fixture (minimal raw PDF): {output_path}")


if __name__ == "__main__":
    fixture_dir = os.path.join(os.path.dirname(__file__), '..', 'fixtures')
    os.makedirs(fixture_dir, exist_ok=True)
    output_path = os.path.join(fixture_dir, 'hdfc_sample.pdf')

    if USE_REPORTLAB:
        generate_with_reportlab(output_path)
    elif USE_FPDF:
        generate_with_fpdf(output_path)
    else:
        generate_minimal_pdf(output_path)
