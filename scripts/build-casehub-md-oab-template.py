#!/usr/bin/env python3
"""Build CaseHub.md OAB reference.docx.

Customiza o reference.docx default do Pandoc para a praxe brasileira:
- Fonte: Times New Roman 12pt
- Margens: 3cm sup, 3cm esq, 2cm inf, 2cm dir (ABNT NBR 14724 / praxe OAB)
- Espaçamento: 1.5
- Alinhamento body: justify
- Recuo de primeira linha: 0 (sem indent — paragrafação por bloco)
"""
import sys
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

SRC = Path("/tmp/pandoc-default-ref.docx")
DST = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/oab.docx")

FONT = "Times New Roman"
BODY_SIZE = Pt(12)

doc = Document(str(SRC))

# 1) Page setup: margens OAB (ABNT)
for section in doc.sections:
    section.top_margin = Cm(3)
    section.left_margin = Cm(3)
    section.bottom_margin = Cm(2)
    section.right_margin = Cm(2)

# 2) Estilos: Normal (body) + Headings
styles = doc.styles

def force_font(style, size=None, bold=None):
    rPr = style.element.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
    )
    f = style.font
    f.name = FONT
    # Set East Asia / complex font names too (Word fallback)
    rFonts = f.element if hasattr(f, 'element') else None
    if size is not None:
        f.size = size
    if bold is not None:
        f.bold = bold


def force_paragraph(style, align=None, line_spacing=None, space_before=None, space_after=None,
                    first_line_indent=None):
    pf = style.paragraph_format
    if align is not None:
        pf.alignment = align
    if line_spacing is not None:
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = line_spacing
    if space_before is not None:
        pf.space_before = space_before
    if space_after is not None:
        pf.space_after = space_after
    if first_line_indent is not None:
        pf.first_line_indent = first_line_indent


# Normal body
if "Normal" in [s.name for s in styles]:
    normal = styles["Normal"]
    force_font(normal, size=BODY_SIZE)
    force_paragraph(
        normal,
        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
        line_spacing=1.5,
        space_before=Pt(0),
        space_after=Pt(6),
        first_line_indent=Cm(0),
    )

# Body Text (Pandoc usa "First Paragraph", "Body Text" etc.)
for sname in ("Body Text", "First Paragraph", "Compact"):
    try:
        s = styles[sname]
        force_font(s, size=BODY_SIZE)
        force_paragraph(s, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line_spacing=1.5)
    except KeyError:
        pass

# Headings (Title 1-6)
heading_sizes = {
    "Heading 1": Pt(16),
    "Heading 2": Pt(14),
    "Heading 3": Pt(13),
    "Heading 4": Pt(12),
    "Heading 5": Pt(12),
    "Heading 6": Pt(12),
    "Title": Pt(18),
}
for hname, hsize in heading_sizes.items():
    try:
        s = styles[hname]
        force_font(s, size=hsize, bold=True)
        force_paragraph(
            s,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            line_spacing=1.15,
            space_before=Pt(12),
            space_after=Pt(6),
        )
    except KeyError:
        pass

# Block Quote (citação)
for qname in ("Quote", "Block Text", "Intense Quote"):
    try:
        s = styles[qname]
        force_font(s, size=Pt(11))
        force_paragraph(s, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line_spacing=1.5)
    except KeyError:
        pass

# Code (verbatim)
for cname in ("Source Code", "Verbatim Char"):
    try:
        s = styles[cname]
        # Manter mono p/ trechos legais (citação de lei/jurisprudência verbatim)
        s.font.name = "Courier New"
        s.font.size = Pt(10)
    except KeyError:
        pass

# Table styles — defer; Pandoc gera tabelas decentes por default

doc.save(str(DST))
print(f"OAB reference.docx saved: {DST}")
print(f"  Margins: 3/3/2/2 cm (top/left/bottom/right)")
print(f"  Font: {FONT} 12pt body, 16/14/13pt headings")
print(f"  Line spacing: 1.5; body alignment: justify")
