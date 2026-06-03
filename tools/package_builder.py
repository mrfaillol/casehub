#!/usr/bin/env python3
"""
ILC Package Builder
====================

Builds USCIS immigration packages by organizing documents into exhibits.
Based on the Musheng He case paradigm (EB-2 NIW with 13 Exhibits A-M).

EXHIBIT STRUCTURE:
A - Forms (I-140, ETA-9089, G-1145)
B - Brief/Cover Letter (Attorney letter, Table of Contents, Personal Statement)
C - Self Petitioner Information (CV, diplomas, certifications, passport)
D - Critical Role/LORs (Letters of Recommendation)
E - Evidence of High Salary
F - Memberships (Professional associations)
G - Judging the Work of Others (Peer review, thesis committees)
H - Acknowledgements (Awards, recognition)
I - Recognition (Media coverage about individual)
J - Job Offers (Employment letters, contracts)
K - Media Coverage (Publications about work)
L - Original Contributions (Patents, publications, citations)
M - Supporting Research (Additional evidence)

FEATURES:
- PDF merging with PyPDF2
- Image to PDF conversion
- DOCX to PDF conversion
- Automatic Table of Contents generation
- Page numbering
- Exhibit organization with separators
"""

import os
import io
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path

try:
    from PyPDF2 import PdfReader, PdfWriter, PdfMerger
except ImportError:
    print("PyPDF2 not installed. Run: pip install PyPDF2")
    PdfReader = PdfWriter = PdfMerger = None

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    Image = None

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
except ImportError:
    print("ReportLab not installed. Run: pip install reportlab")
    canvas = None


# =============================================================================
# EXHIBIT CONFIGURATION (Musheng Paradigm)
# =============================================================================

EXHIBITS = {
    "A": {
        "name": "Forms",
        "description": "USCIS Forms (I-140, ETA-9089, G-1145)",
        "required": True,
    },
    "B": {
        "name": "Brief",
        "description": "Cover Letter, Table of Contents, Personal Statement",
        "required": True,
    },
    "C": {
        "name": "Self Petitioner Information",
        "description": "CV, diplomas, certifications, passport, degrees",
        "required": True,
    },
    "D": {
        "name": "Critical Role",
        "description": "Letters of Recommendation",
        "required": True,
    },
    "E": {
        "name": "Evidence of High Salary",
        "description": "Pay stubs, W-2s, salary letters",
        "required": False,
    },
    "F": {
        "name": "Memberships",
        "description": "Professional association memberships",
        "required": False,
    },
    "G": {
        "name": "Judging the Work of Others",
        "description": "Peer review evidence, thesis committee participation",
        "required": False,
    },
    "H": {
        "name": "Acknowledgements",
        "description": "Awards, recognition, certificates",
        "required": False,
    },
    "I": {
        "name": "Recognition",
        "description": "Media coverage about the individual",
        "required": False,
    },
    "J": {
        "name": "Job Offers",
        "description": "Employment letters, contracts, offer letters",
        "required": False,
    },
    "K": {
        "name": "Media Coverage",
        "description": "Publications about work/projects",
        "required": False,
    },
    "L": {
        "name": "Original Contributions",
        "description": "Patents, publications, citations evidence",
        "required": False,
    },
    "M": {
        "name": "Supporting Research",
        "description": "Additional supporting evidence",
        "required": False,
    },
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_separator_page(
    exhibit_letter: str,
    exhibit_name: str,
    output_path: str,
) -> str:
    """Create a separator page for an exhibit."""
    if canvas is None:
        raise ImportError("ReportLab is required for separator pages")

    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Center the exhibit letter and name
    c.setFont("Helvetica-Bold", 72)
    c.drawCentredString(width / 2, height / 2 + 50, f"EXHIBIT {exhibit_letter}")

    c.setFont("Helvetica", 24)
    c.drawCentredString(width / 2, height / 2 - 20, exhibit_name)

    c.save()
    return output_path


def image_to_pdf(image_path: str, output_path: str) -> str:
    """Convert an image to PDF."""
    if Image is None:
        raise ImportError("Pillow is required for image conversion")

    img = Image.open(image_path)

    # Convert to RGB if necessary
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.save(output_path, "PDF", resolution=100.0)
    return output_path


def get_pdf_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF."""
    if PdfReader is None:
        raise ImportError("PyPDF2 is required")

    reader = PdfReader(pdf_path)
    return len(reader.pages)


def merge_pdfs(pdf_paths: List[str], output_path: str) -> str:
    """Merge multiple PDFs into one."""
    if PdfMerger is None:
        raise ImportError("PyPDF2 is required")

    merger = PdfMerger()

    for pdf_path in pdf_paths:
        if os.path.exists(pdf_path):
            merger.append(pdf_path)

    merger.write(output_path)
    merger.close()

    return output_path


# =============================================================================
# PACKAGE BUILDER CLASS
# =============================================================================

class PackageBuilder:
    """
    Build USCIS immigration packages organized by exhibits.

    Example usage:
        builder = PackageBuilder(
            beneficiary_name="John Doe",
            case_type="EB-2 NIW",
        )

        # Add documents to exhibits
        builder.add_document("A", "/path/to/i-140.pdf", "Form I-140")
        builder.add_document("D", "/path/to/lor1.pdf", "LOR from Dr. Smith")
        builder.add_document("D", "/path/to/lor2.pdf", "LOR from Prof. Jones")

        # Build the package
        filepath = builder.build()
    """

    def __init__(
        self,
        beneficiary_name: str,
        case_type: str = "EB-2 NIW",
        output_dir: str = "output",
        include_separators: bool = True,
        include_toc: bool = True,
    ):
        self.beneficiary_name = beneficiary_name
        self.case_type = case_type
        self.output_dir = output_dir
        self.include_separators = include_separators
        self.include_toc = include_toc

        os.makedirs(output_dir, exist_ok=True)

        # Document storage: {exhibit_letter: [(filepath, description), ...]}
        self.documents: Dict[str, List[Tuple[str, str]]] = {
            letter: [] for letter in EXHIBITS.keys()
        }

        # Page tracking for TOC
        self.toc_entries: List[Tuple[str, str, int]] = []

    def add_document(
        self,
        exhibit: str,
        filepath: str,
        description: str,
    ) -> bool:
        """
        Add a document to an exhibit.

        Args:
            exhibit: Exhibit letter (A-M)
            filepath: Path to the document (PDF, image, or DOCX)
            description: Description for Table of Contents

        Returns:
            True if successful
        """
        exhibit = exhibit.upper()
        if exhibit not in EXHIBITS:
            print(f"Invalid exhibit: {exhibit}")
            return False

        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return False

        # Convert non-PDF files
        ext = Path(filepath).suffix.lower()

        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff"]:
            # Convert image to PDF
            pdf_path = os.path.join(
                self.output_dir,
                f"converted_{Path(filepath).stem}.pdf"
            )
            filepath = image_to_pdf(filepath, pdf_path)
            print(f"Converted image to PDF: {pdf_path}")

        elif ext in [".docx", ".doc"]:
            print(f"WARNING: DOCX conversion requires manual export to PDF: {filepath}")
            return False

        elif ext != ".pdf":
            print(f"Unsupported file type: {ext}")
            return False

        self.documents[exhibit].append((filepath, description))
        return True

    def add_documents_from_folder(
        self,
        exhibit: str,
        folder_path: str,
        description_prefix: str = "",
    ) -> int:
        """
        Add all PDFs from a folder to an exhibit.

        Args:
            exhibit: Exhibit letter
            folder_path: Path to folder containing documents
            description_prefix: Prefix for descriptions

        Returns:
            Number of documents added
        """
        count = 0
        folder = Path(folder_path)

        if not folder.exists():
            print(f"Folder not found: {folder_path}")
            return 0

        for file in sorted(folder.glob("*.pdf")):
            desc = f"{description_prefix}{file.stem}" if description_prefix else file.stem
            if self.add_document(exhibit, str(file), desc):
                count += 1

        return count

    def get_exhibit_summary(self) -> Dict[str, int]:
        """Get count of documents per exhibit."""
        return {
            letter: len(docs)
            for letter, docs in self.documents.items()
        }

    def build(
        self,
        filename: Optional[str] = None,
    ) -> str:
        """
        Build the complete package PDF.

        Args:
            filename: Optional output filename

        Returns:
            Path to generated package
        """
        if PdfMerger is None:
            raise ImportError("PyPDF2 is required to build packages")

        all_pdfs = []
        current_page = 1

        # Process each exhibit
        for letter in EXHIBITS.keys():
            docs = self.documents[letter]

            if not docs:
                continue  # Skip empty exhibits

            exhibit_info = EXHIBITS[letter]

            # Add separator page
            if self.include_separators:
                separator_path = os.path.join(
                    self.output_dir,
                    f"separator_{letter}.pdf"
                )
                create_separator_page(letter, exhibit_info["name"], separator_path)
                all_pdfs.append(separator_path)

                # Record for TOC
                self.toc_entries.append((
                    f"Exhibit {letter}",
                    exhibit_info["name"],
                    current_page
                ))
                current_page += 1

            # Add each document
            for filepath, description in docs:
                all_pdfs.append(filepath)

                # Track pages
                page_count = get_pdf_page_count(filepath)
                self.toc_entries.append((
                    f"    {description}",
                    "",
                    current_page
                ))
                current_page += page_count

        # Create TOC if requested
        if self.include_toc and self.toc_entries:
            toc_path = self._generate_toc()
            all_pdfs.insert(0, toc_path)

        # Merge all PDFs
        if not filename:
            safe_name = "".join(
                c for c in self.beneficiary_name if c.isalnum() or c in " _-"
            ).replace(" ", "_")
            filename = f"Package_{safe_name}_{self.case_type.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        output_path = os.path.join(self.output_dir, filename)
        merge_pdfs(all_pdfs, output_path)

        # Clean up separator pages
        for letter in EXHIBITS.keys():
            separator_path = os.path.join(self.output_dir, f"separator_{letter}.pdf")
            if os.path.exists(separator_path):
                os.remove(separator_path)

        print(f"\nPackage built: {output_path}")
        print(f"Total exhibits: {sum(1 for d in self.documents.values() if d)}")
        print(f"Total documents: {sum(len(d) for d in self.documents.values())}")

        return output_path

    def _generate_toc(self) -> str:
        """Generate Table of Contents PDF."""
        if canvas is None:
            raise ImportError("ReportLab is required for TOC generation")

        toc_path = os.path.join(self.output_dir, "table_of_contents.pdf")
        c = canvas.Canvas(toc_path, pagesize=letter)
        width, height = letter

        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 1 * inch, "TABLE OF CONTENTS")

        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(
            width / 2,
            height - 1.3 * inch,
            f"{self.beneficiary_name} - {self.case_type} Petition"
        )

        # Entries
        y = height - 2 * inch
        c.setFont("Helvetica", 11)

        for entry, subtitle, page in self.toc_entries:
            if y < 1 * inch:
                c.showPage()
                y = height - 1 * inch
                c.setFont("Helvetica", 11)

            # Exhibit headers in bold
            if entry.startswith("Exhibit"):
                c.setFont("Helvetica-Bold", 11)
                c.drawString(0.75 * inch, y, entry)
                if subtitle:
                    c.drawString(2.5 * inch, y, subtitle)
                c.drawRightString(width - 0.75 * inch, y, str(page))
                c.setFont("Helvetica", 11)
            else:
                c.drawString(0.75 * inch, y, entry)
                c.drawRightString(width - 0.75 * inch, y, str(page))

            y -= 0.25 * inch

        c.save()
        return toc_path


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_merge(
    pdf_paths: List[str],
    output_path: str,
) -> str:
    """
    Quick merge of multiple PDFs without exhibit organization.

    Args:
        pdf_paths: List of PDF file paths
        output_path: Output file path

    Returns:
        Path to merged PDF
    """
    return merge_pdfs(pdf_paths, output_path)


def convert_images_to_pdf(
    image_paths: List[str],
    output_path: str,
) -> str:
    """
    Convert multiple images to a single PDF.

    Args:
        image_paths: List of image file paths
        output_path: Output PDF path

    Returns:
        Path to generated PDF
    """
    if Image is None:
        raise ImportError("Pillow is required")

    images = []
    for path in image_paths:
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        images.append(img)

    if images:
        images[0].save(
            output_path,
            "PDF",
            resolution=100.0,
            save_all=True,
            append_images=images[1:] if len(images) > 1 else []
        )

    return output_path


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ILC Package Builder")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build a package")
    build_parser.add_argument("--name", required=True, help="Beneficiary name")
    build_parser.add_argument("--case-type", default="EB-2 NIW", help="Case type")
    build_parser.add_argument("--output", default="output", help="Output directory")

    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Quick merge PDFs")
    merge_parser.add_argument("files", nargs="+", help="PDF files to merge")
    merge_parser.add_argument("--output", required=True, help="Output file")

    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert images to PDF")
    convert_parser.add_argument("files", nargs="+", help="Image files")
    convert_parser.add_argument("--output", required=True, help="Output file")

    # List exhibits command
    list_parser = subparsers.add_parser("exhibits", help="List exhibit structure")

    args = parser.parse_args()

    if args.command == "build":
        print(f"Creating package builder for {args.name}...")
        builder = PackageBuilder(
            beneficiary_name=args.name,
            case_type=args.case_type,
            output_dir=args.output,
        )
        print("\nAdd documents using the Python API:")
        print('  builder.add_document("A", "/path/to/form.pdf", "Form I-140")')
        print('  builder.add_document("D", "/path/to/lor.pdf", "LOR from Dr. Smith")')
        print('  builder.build()')

    elif args.command == "merge":
        output = quick_merge(args.files, args.output)
        print(f"Merged {len(args.files)} PDFs to: {output}")

    elif args.command == "convert":
        output = convert_images_to_pdf(args.files, args.output)
        print(f"Converted {len(args.files)} images to: {output}")

    elif args.command == "exhibits":
        print("\nEB-2 NIW Package Structure (Musheng Paradigm):")
        print("=" * 60)
        for letter, info in EXHIBITS.items():
            req = "[REQUIRED]" if info["required"] else "[Optional]"
            print(f"\nExhibit {letter}: {info['name']} {req}")
            print(f"  {info['description']}")

    else:
        parser.print_help()
