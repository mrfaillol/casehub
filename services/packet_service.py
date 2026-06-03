"""
CaseHub - Document Packet Service
Create document packets by merging multiple documents into a single PDF.
"""
import os
from datetime import datetime
from io import BytesIO
from typing import List, Optional
import uuid

try:
    from PyPDF2 import PdfMerger, PdfReader, PdfWriter
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class PacketService:
    """Service for creating document packets."""

    OUTPUT_DIR = "uploads/packets"

    def __init__(self):
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    def create_packet(
        self,
        documents: List[dict],
        title: str = "Document Packet",
        include_toc: bool = True,
        include_cover: bool = True,
        case_info: dict = None
    ) -> dict:
        """Create a document packet from multiple documents.

        Args:
            documents: List of dicts with 'filepath' and 'name' keys
            title: Title for the packet
            include_toc: Whether to include table of contents
            include_cover: Whether to include cover page
            case_info: Optional case information for cover page

        Returns:
            Dictionary with packet info or error
        """
        if not PYPDF2_AVAILABLE:
            return {"success": False, "error": "PyPDF2 not available for PDF merging"}

        try:
            merger = PdfMerger()
            toc_items = []
            current_page = 1

            # Generate cover page if requested
            if include_cover:
                cover_pdf = self._generate_cover_page(title, case_info, documents)
                if cover_pdf:
                    merger.append(BytesIO(cover_pdf))
                    current_page += 1  # Cover is typically 1 page

            # Generate TOC if requested
            if include_toc:
                # We'll calculate page numbers as we go
                toc_start_page = current_page

            # Add each document
            for doc in documents:
                filepath = doc.get('filepath')
                doc_name = doc.get('name', 'Untitled')

                if not filepath or not os.path.exists(filepath):
                    continue

                # Get page count before merging
                try:
                    reader = PdfReader(filepath)
                    page_count = len(reader.pages)
                except:
                    page_count = 1

                # Record TOC entry
                toc_items.append({
                    'name': doc_name,
                    'page': current_page + (2 if include_toc else 0),  # Account for TOC pages
                    'page_count': page_count
                })

                # Merge the document
                try:
                    merger.append(filepath)
                    current_page += page_count
                except Exception as e:
                    # Skip problematic PDFs
                    toc_items.pop()  # Remove the TOC entry
                    continue

            # Generate and insert TOC if requested
            if include_toc and toc_items:
                toc_pdf = self._generate_toc(title, toc_items)
                if toc_pdf:
                    # Insert TOC after cover
                    merger.merge(1 if include_cover else 0, BytesIO(toc_pdf))

            # Generate unique filename
            packet_id = str(uuid.uuid4())[:8]
            filename = f"packet_{packet_id}.pdf"
            filepath = os.path.join(self.OUTPUT_DIR, filename)

            # Write the merged PDF
            with open(filepath, 'wb') as f:
                merger.write(f)

            merger.close()

            # Get final page count
            try:
                reader = PdfReader(filepath)
                total_pages = len(reader.pages)
            except:
                total_pages = len(documents)

            return {
                "success": True,
                "packet_id": packet_id,
                "filepath": filepath,
                "filename": filename,
                "title": title,
                "document_count": len(documents),
                "total_pages": total_pages,
                "created_at": datetime.now().isoformat()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_cover_page(self, title: str, case_info: dict = None, documents: List[dict] = None) -> Optional[bytes]:
        """Generate a cover page PDF."""
        if not REPORTLAB_AVAILABLE:
            return None

        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2*inch, bottomMargin=1*inch)

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('CoverTitle', parent=styles['Title'], fontSize=28, spaceAfter=30, alignment=TA_CENTER)
            subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=14, textColor=colors.grey, alignment=TA_CENTER)
            normal_style = styles['Normal']
            center_style = ParagraphStyle('Center', parent=normal_style, alignment=TA_CENTER)

            elements = []

            # Company header
            elements.append(Paragraph("IMMIGRATION LAW CENTER", subtitle_style))
            elements.append(Spacer(1, 40))

            # Title
            elements.append(Paragraph(title, title_style))
            elements.append(Spacer(1, 30))

            # Case info if provided
            if case_info:
                if case_info.get('case_number'):
                    elements.append(Paragraph(f"<b>Case Number:</b> {case_info['case_number']}", center_style))
                if case_info.get('case_name'):
                    elements.append(Paragraph(f"<b>Case:</b> {case_info['case_name']}", center_style))
                if case_info.get('client_name'):
                    elements.append(Paragraph(f"<b>Client:</b> {case_info['client_name']}", center_style))
                elements.append(Spacer(1, 30))

            # Date
            elements.append(Paragraph(f"<b>Date Prepared:</b> {datetime.now().strftime('%B %d, %Y')}", center_style))

            # Document count
            if documents:
                elements.append(Spacer(1, 20))
                elements.append(Paragraph(f"<b>Documents Included:</b> {len(documents)}", center_style))

            # Footer
            elements.append(Spacer(1, 100))
            from config import settings
            elements.append(Paragraph(settings.ORG_NAME, center_style))
            elements.append(Paragraph(f"{settings.ORG_EMAIL}", center_style))

            doc.build(elements)
            return buffer.getvalue()

        except Exception as e:
            return None

    def _generate_toc(self, title: str, toc_items: List[dict]) -> Optional[bytes]:
        """Generate a table of contents PDF."""
        if not REPORTLAB_AVAILABLE:
            return None

        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1*inch, bottomMargin=1*inch)

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('TOCTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=30, alignment=TA_CENTER)
            item_style = styles['Normal']

            elements = []

            # Title
            elements.append(Paragraph("TABLE OF CONTENTS", title_style))
            elements.append(Spacer(1, 20))

            # Build TOC table
            table_data = [['#', 'Document', 'Page']]
            for i, item in enumerate(toc_items, 1):
                table_data.append([
                    str(i),
                    item['name'][:60] + ('...' if len(item['name']) > 60 else ''),
                    str(item['page'])
                ])

            table = Table(table_data, colWidths=[0.5*inch, 5*inch, 0.75*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))

            elements.append(table)

            doc.build(elements)
            return buffer.getvalue()

        except Exception as e:
            return None

    def delete_packet(self, filepath: str) -> bool:
        """Delete a packet file."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            return False
        except:
            return False


# SQL for packets table
CREATE_PACKETS_TABLE = """
CREATE TABLE IF NOT EXISTS document_packets (
    id SERIAL PRIMARY KEY,
    packet_id VARCHAR(20) UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id),
    title VARCHAR(200) NOT NULL,
    filepath VARCHAR(500) NOT NULL,
    document_count INTEGER DEFAULT 0,
    total_pages INTEGER DEFAULT 0,
    include_toc BOOLEAN DEFAULT true,
    include_cover BOOLEAN DEFAULT true,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_packets_case ON document_packets(case_id);
CREATE INDEX IF NOT EXISTS idx_packets_id ON document_packets(packet_id);

CREATE TABLE IF NOT EXISTS packet_documents (
    id SERIAL PRIMARY KEY,
    packet_id INTEGER REFERENCES document_packets(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id),
    document_name VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_packet_docs_packet ON packet_documents(packet_id);
"""


# Singleton instance
packet_service = PacketService()
