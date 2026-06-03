"""
CaseHub - PDF Generation Service
Generate PDF invoices and documents using weasyprint or reportlab fallback.
"""
from datetime import datetime, date
from io import BytesIO
import os

from config import settings

# Try to import weasyprint, fall back to reportlab
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class PDFService:
    """Service for generating PDF documents."""

    def __init__(self):
        self.company_name = settings.ORG_NAME
        self.company_address = os.getenv("ORG_ADDRESS", "")
        self.company_phone = os.getenv("ORG_PHONE", "")
        self.company_email = settings.ORG_EMAIL
        self.company_website = f"https://{settings.ORG_DOMAIN}" if settings.ORG_DOMAIN else settings.BASE_URL

    def generate_invoice_pdf(self, invoice_data: dict) -> bytes:
        """Generate a PDF invoice.

        Args:
            invoice_data: Dictionary containing:
                - invoice_number: str
                - client_name: str
                - client_address: str (optional)
                - client_email: str (optional)
                - case_name: str (optional)
                - items: list of dicts with description, amount
                - subtotal: float
                - tax: float (optional)
                - total: float
                - due_date: date
                - invoice_date: date
                - notes: str (optional)
                - paid: bool

        Returns:
            PDF as bytes
        """
        if WEASYPRINT_AVAILABLE:
            return self._generate_with_weasyprint(invoice_data)
        elif REPORTLAB_AVAILABLE:
            return self._generate_with_reportlab(invoice_data)
        else:
            raise RuntimeError("No PDF library available. Install weasyprint or reportlab.")

    def _generate_with_weasyprint(self, data: dict) -> bytes:
        """Generate PDF using WeasyPrint (better styling support)."""
        html_content = self._build_invoice_html(data)
        css = CSS(string='''
            @page {
                size: letter;
                margin: 0.5in;
            }
            body {
                font-family: Arial, Helvetica, sans-serif;
                font-size: 10pt;
                line-height: 1.4;
            }
            h1 { font-size: 24pt; color: #333; }
            h2 { font-size: 14pt; color: #666; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 8px; text-align: left; }
            th { background-color: #f8f9fa; }
            .amount { text-align: right; }
            .total-row { font-weight: bold; background-color: #e9ecef; }
            .paid-stamp {
                color: #28a745;
                font-size: 48pt;
                transform: rotate(-30deg);
                position: absolute;
                opacity: 0.3;
            }
        ''')

        html = HTML(string=html_content)
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer, stylesheets=[css])
        return pdf_buffer.getvalue()

    def _generate_with_reportlab(self, data: dict) -> bytes:
        """Generate PDF using ReportLab (fallback)."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=24, spaceAfter=20)
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, textColor=colors.grey)
        normal_style = styles['Normal']
        right_style = ParagraphStyle('Right', parent=styles['Normal'], alignment=TA_RIGHT)

        elements = []

        # Header
        elements.append(Paragraph(self.company_name, title_style))
        elements.append(Paragraph(self.company_address.replace('\n', '<br/>'), normal_style))
        elements.append(Paragraph(f"{self.company_phone} | {self.company_email}", normal_style))
        elements.append(Spacer(1, 30))

        # Invoice Title
        elements.append(Paragraph(f"INVOICE #{data.get('invoice_number', 'N/A')}", title_style))

        # Invoice Info Table
        invoice_date = data.get('invoice_date', date.today())
        due_date = data.get('due_date')
        if isinstance(invoice_date, datetime):
            invoice_date = invoice_date.date()

        info_data = [
            ['Invoice Date:', invoice_date.strftime('%B %d, %Y') if invoice_date else 'N/A'],
            ['Due Date:', due_date.strftime('%B %d, %Y') if due_date else 'Upon Receipt'],
            ['Status:', 'PAID' if data.get('paid') else 'PENDING'],
        ]
        info_table = Table(info_data, colWidths=[100, 200])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (1, 2), (1, 2), colors.green if data.get('paid') else colors.red),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 20))

        # Client Info
        elements.append(Paragraph('Bill To:', heading_style))
        elements.append(Paragraph(data.get('client_name', 'N/A'), styles['Heading3']))
        if data.get('client_address'):
            elements.append(Paragraph(data['client_address'].replace('\n', '<br/>'), normal_style))
        if data.get('client_email'):
            elements.append(Paragraph(data['client_email'], normal_style))
        elements.append(Spacer(1, 20))

        # Case Info
        if data.get('case_name'):
            elements.append(Paragraph(f"Case: {data['case_name']}", normal_style))
            elements.append(Spacer(1, 10))

        # Items Table
        items = data.get('items', [])
        table_data = [['Description', 'Amount']]
        for item in items:
            table_data.append([
                item.get('description', ''),
                f"${item.get('amount', 0):,.2f}"
            ])

        # Totals
        table_data.append(['', ''])
        table_data.append(['Subtotal:', f"${data.get('subtotal', 0):,.2f}"])
        if data.get('tax', 0) > 0:
            table_data.append(['Tax:', f"${data.get('tax', 0):,.2f}"])
        table_data.append(['TOTAL:', f"${data.get('total', 0):,.2f}"])

        items_table = Table(table_data, colWidths=[400, 100])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, len(items)), 0.5, colors.grey),
            ('LINEBELOW', (0, -3), (-1, -3), 1, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 30))

        # Notes
        if data.get('notes'):
            elements.append(Paragraph('Notes:', heading_style))
            elements.append(Paragraph(data['notes'], normal_style))
            elements.append(Spacer(1, 20))

        # Footer
        elements.append(Spacer(1, 30))
        elements.append(Paragraph('Thank you for your business!', ParagraphStyle('Center', parent=normal_style, alignment=TA_CENTER)))
        elements.append(Paragraph(f'{self.company_website}', ParagraphStyle('Center', parent=normal_style, alignment=TA_CENTER, textColor=colors.blue)))

        doc.build(elements)
        return buffer.getvalue()

    def _build_invoice_html(self, data: dict) -> str:
        """Build HTML for invoice (used by WeasyPrint)."""
        invoice_date = data.get('invoice_date', date.today())
        due_date = data.get('due_date')
        if isinstance(invoice_date, datetime):
            invoice_date = invoice_date.date()

        items_html = ""
        for item in data.get('items', []):
            items_html += f"""
            <tr>
                <td>{item.get('description', '')}</td>
                <td class="amount">${item.get('amount', 0):,.2f}</td>
            </tr>
            """

        paid_stamp = '<div class="paid-stamp">PAID</div>' if data.get('paid') else ''

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Invoice {data.get('invoice_number', '')}</title>
        </head>
        <body>
            {paid_stamp}
            <div style="display: flex; justify-content: space-between; margin-bottom: 40px;">
                <div>
                    <h1>{self.company_name}</h1>
                    <p>{self.company_address.replace(chr(10), '<br>')}</p>
                    <p>{self.company_phone} | {self.company_email}</p>
                </div>
                <div style="text-align: right;">
                    <h2>INVOICE</h2>
                    <p><strong>#{data.get('invoice_number', 'N/A')}</strong></p>
                    <p>Date: {invoice_date.strftime('%B %d, %Y') if invoice_date else 'N/A'}</p>
                    <p>Due: {due_date.strftime('%B %d, %Y') if due_date else 'Upon Receipt'}</p>
                </div>
            </div>

            <div style="margin-bottom: 30px;">
                <h2>Bill To:</h2>
                <p><strong>{data.get('client_name', 'N/A')}</strong></p>
                <p>{data.get('client_address', '').replace(chr(10), '<br>') if data.get('client_address') else ''}</p>
                <p>{data.get('client_email', '')}</p>
            </div>

            {'<p><strong>Case:</strong> ' + data.get('case_name') + '</p>' if data.get('case_name') else ''}

            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th class="amount">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
                <tfoot>
                    <tr>
                        <td><strong>Subtotal</strong></td>
                        <td class="amount"><strong>${data.get('subtotal', 0):,.2f}</strong></td>
                    </tr>
                    {'<tr><td>Tax</td><td class="amount">${:,.2f}</td></tr>'.format(data.get('tax', 0)) if data.get('tax', 0) > 0 else ''}
                    <tr class="total-row">
                        <td><strong>TOTAL</strong></td>
                        <td class="amount"><strong>${data.get('total', 0):,.2f}</strong></td>
                    </tr>
                </tfoot>
            </table>

            {'<div style="margin-top: 30px;"><h3>Notes:</h3><p>' + data.get('notes', '') + '</p></div>' if data.get('notes') else ''}

            <div style="margin-top: 50px; text-align: center;">
                <p>Thank you for your business!</p>
                <p><a href="{self.company_website}">{self.company_website}</a></p>
            </div>
        </body>
        </html>
        """


# Singleton instance
pdf_service = PDFService()
