"""
CaseHub - Form Filler Service
Fills USCIS PDF forms with intake questionnaire response data.
This is the "game changer" per Daniel: client fills questionnaire once,
data auto-populates all USCIS forms.

Uses PyPDF2 to fill AcroForm fields in official USCIS fillable PDFs.
Falls back to generating a summary PDF with ReportLab if fillable PDF not available.
"""
import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Base directory for USCIS form templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USCIS_PDF_DIR = os.path.join(BASE_DIR, "data", "uscis_forms")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "output")

# Template IDs from intake_service.py
TEMPLATE_IDS = {
    "G-28": 52,
    "I-130": 38,
    "I-130A": None,  # Sub-form of I-130
    "I-131": 43,
    "I-140": 19,
    "I-485": 40,
    "I-765": 42,
    "I-864": 41,
    "I-907": 13,
    "COMMON-INFO": 59,
}

# Reverse mapping: template_id -> form name
TEMPLATE_NAMES = {v: k for k, v in TEMPLATE_IDS.items() if v is not None}

# Forms required per visa type
VISA_FORM_PACKAGES = {
    "EB-1A": ["G-28", "I-140", "I-907"],
    "EB-2 NIW": ["G-28", "I-140", "I-907"],
    "EB-1B": ["G-28", "I-140"],
    "O-1A": ["G-28", "I-129"],
    "Family-Based": ["G-28", "I-130", "I-485", "I-864", "I-765", "I-131"],
    "IR-1": ["G-28", "I-130", "I-485", "I-864", "I-765", "I-131"],
}

# Attorney info (auto-filled in G-28 and preparer sections)
# Configure in .env or admin settings
from config import settings
ATTORNEY_INFO = {
    "p1_2a_family_name": os.getenv("ATTORNEY_LAST_NAME", ""),
    "p1_2b_given_name": os.getenv("ATTORNEY_FIRST_NAME", ""),
    "p1_4_firm_name": settings.ORG_NAME,
    "p1_5a_street": os.getenv("FIRM_STREET", ""),
    "p1_5c_city": os.getenv("FIRM_CITY", ""),
    "p1_5d_state": os.getenv("FIRM_STATE", ""),
    "p1_5e_zip": os.getenv("FIRM_ZIP", ""),
    "p1_6_phone": os.getenv("FIRM_PHONE", ""),
    "p1_8_email": settings.ORG_EMAIL,
}


class FormFillerService:
    """Service to fill USCIS PDF forms with intake questionnaire data."""

    def __init__(self):
        self._field_maps = None
        os.makedirs(USCIS_PDF_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    @property
    def field_maps(self):
        """Lazy-load field maps to avoid import issues at startup."""
        if self._field_maps is None:
            try:
                from services.form_field_maps import FORM_FIELD_MAPS
                self._field_maps = FORM_FIELD_MAPS
            except ImportError:
                logger.warning("form_field_maps.py not found, using empty maps")
                self._field_maps = {}
        return self._field_maps

    def get_available_forms(self) -> List[Dict]:
        """List forms that can be auto-filled (have both PDF template and field map)."""
        available = []
        for form_name, template_id in TEMPLATE_IDS.items():
            if form_name == "COMMON-INFO":
                continue
            pdf_path = self._get_pdf_path(form_name)
            has_pdf = pdf_path is not None and os.path.exists(pdf_path)
            has_map = form_name in self.field_maps and len(self.field_maps.get(form_name, {})) > 0
            available.append({
                "form_name": form_name,
                "template_id": template_id,
                "has_pdf": has_pdf,
                "has_field_map": has_map,
                "can_fill": has_pdf and has_map,
                "field_count": len(self.field_maps.get(form_name, {})),
            })
        return available

    def get_forms_for_visa(self, visa_type: str) -> List[str]:
        """Get the list of forms needed for a visa type."""
        return VISA_FORM_PACKAGES.get(visa_type, ["G-28"])

    def fill_form(
        self,
        form_name: str,
        response_data: Dict,
        common_info: Optional[Dict] = None,
        attorney_info: Optional[Dict] = None,
        beneficiary_name: str = "",
    ) -> Tuple[Optional[str], Dict]:
        """
        Fill a USCIS PDF form with response data.

        Returns:
            Tuple of (output_path, stats_dict)
            output_path is None if filling failed
        """
        field_map = self.field_maps.get(form_name)
        if not field_map:
            logger.warning(f"No field map for {form_name}")
            return None, {"error": f"No field map available for {form_name}", "success": False}

        pdf_path = self._get_pdf_path(form_name)

        # Merge data: common-info first, then form-specific (overrides)
        merged_data = {}
        if common_info:
            merged_data.update(common_info)
        merged_data.update(response_data)

        # Try filling the actual PDF
        if pdf_path and os.path.exists(pdf_path):
            return self._fill_acroform_pdf(
                form_name, pdf_path, field_map, merged_data,
                attorney_info or ATTORNEY_INFO, beneficiary_name
            )
        else:
            # Generate a summary PDF with the data instead
            return self._generate_summary_pdf(
                form_name, field_map, merged_data,
                attorney_info or ATTORNEY_INFO, beneficiary_name
            )

    def fill_all_forms(
        self,
        visa_type: str,
        responses_by_template: Dict[int, Dict],
        common_info: Optional[Dict] = None,
        beneficiary_name: str = "",
    ) -> List[Dict]:
        """
        Fill all forms for a visa type.

        Args:
            visa_type: e.g., "EB-2 NIW"
            responses_by_template: {template_id: {field: value, ...}, ...}
            common_info: COMMON-INFO response data (shared across forms)
            beneficiary_name: Client name for filenames

        Returns:
            List of dicts with form results
        """
        forms_needed = self.get_forms_for_visa(visa_type)
        results = []

        for form_name in forms_needed:
            template_id = TEMPLATE_IDS.get(form_name)
            form_data = {}

            # Get response data for this specific form
            if template_id and template_id in responses_by_template:
                form_data = responses_by_template[template_id]

            output_path, stats = self.fill_form(
                form_name=form_name,
                response_data=form_data,
                common_info=common_info,
                beneficiary_name=beneficiary_name,
            )

            results.append({
                "form_name": form_name,
                "template_id": template_id,
                "output_path": output_path,
                "filename": os.path.basename(output_path) if output_path else None,
                **stats,
            })

        return results

    def _get_pdf_path(self, form_name: str) -> Optional[str]:
        """Find the blank USCIS PDF for a form."""
        # Try standard naming conventions
        normalized = form_name.lower().replace("-", "").replace(" ", "")
        candidates = [
            os.path.join(USCIS_PDF_DIR, f"{form_name.lower()}.pdf"),
            os.path.join(USCIS_PDF_DIR, f"{normalized}.pdf"),
            os.path.join(USCIS_PDF_DIR, f"{form_name}.pdf"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def _get_field_hierarchy(self, pdf_path: str) -> Dict[str, str]:
        """Build flat->hierarchical field name lookup via pdftk."""
        import subprocess
        cache_key = pdf_path
        if not hasattr(self, '_hierarchy_cache'):
            self._hierarchy_cache = {}
        if cache_key in self._hierarchy_cache:
            return self._hierarchy_cache[cache_key]

        result = subprocess.run(
            ["pdftk", pdf_path, "dump_data_fields"],
            capture_output=True, text=True, timeout=30
        )
        flat_to_full = {}
        for line in result.stdout.splitlines():
            if line.startswith("FieldName: "):
                full_name = line[len("FieldName: "):]
                # Extract flat name (last component after last dot)
                flat_name = full_name.rsplit(".", 1)[-1] if "." in full_name else full_name
                # Only keep the first occurrence of each flat name
                if flat_name not in flat_to_full:
                    flat_to_full[flat_name] = full_name

        self._hierarchy_cache[cache_key] = flat_to_full
        return flat_to_full

    def _fill_acroform_pdf(
        self,
        form_name: str,
        pdf_path: str,
        field_map: Dict[str, str],
        data: Dict,
        attorney_info: Dict,
        beneficiary_name: str,
    ) -> Tuple[Optional[str], Dict]:
        """Fill a USCIS PDF with XFA/AcroForm fields using pdftk."""
        import subprocess

        try:
            # Build flat->hierarchical field name lookup
            flat_to_full = self._get_field_hierarchy(pdf_path)

            filled_count = 0
            skipped_count = 0
            total_in_map = len(field_map)

            # Build the PDF field values dict (flat name -> value)
            flat_field_values = {}

            # 1. Fill attorney info (for G-28 and preparer sections)
            if form_name == "G-28":
                for our_field, value in attorney_info.items():
                    pdf_field = field_map.get(our_field)
                    if pdf_field and value:
                        flat_field_values[pdf_field] = str(value)
                        filled_count += 1

            # 2. Fill client/form data
            for our_field, value in data.items():
                pdf_field = field_map.get(our_field)
                if pdf_field and value and str(value).strip():
                    str_value = self._format_value(our_field, value)
                    flat_field_values[pdf_field] = str_value
                    filled_count += 1
                elif our_field in field_map:
                    skipped_count += 1

            # Resolve flat names to hierarchical for pdftk FDF
            fdf_fields = []
            unresolved = []
            for flat_name, value in flat_field_values.items():
                full_name = flat_to_full.get(flat_name)
                if full_name:
                    # Escape special characters in FDF values
                    escaped_value = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                    fdf_fields.append(f"<< /T ({full_name}) /V ({escaped_value}) >>")
                else:
                    unresolved.append(flat_name)

            if unresolved:
                logger.warning(f"{form_name}: {len(unresolved)} fields not found in PDF: {unresolved[:5]}")

            # Build FDF file
            fdf_content = "%FDF-1.2\n1 0 obj\n<<\n/FDF\n<<\n/Fields [\n"
            fdf_content += "\n".join(fdf_fields)
            fdf_content += "\n]\n>>\n>>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

            # Write FDF to temp file
            fdf_path = os.path.join(tempfile.gettempdir(), f"fill_{form_name}_{os.getpid()}.fdf")
            with open(fdf_path, "w") as f:
                f.write(fdf_content)

            # Output path
            safe_name = "".join(c for c in beneficiary_name if c.isalnum() or c in " _-")[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"Filled_{form_name}_{safe_name}_{timestamp}.pdf"
            output_path = os.path.join(OUTPUT_DIR, filename)

            # Fill with pdftk
            result = subprocess.run(
                ["pdftk", pdf_path, "fill_form", fdf_path, "output", output_path],
                capture_output=True, text=True, timeout=60
            )

            # Clean up temp FDF
            try:
                os.unlink(fdf_path)
            except OSError:
                pass

            if result.returncode != 0:
                logger.error(f"pdftk error for {form_name}: {result.stderr}")
                return self._generate_summary_pdf(
                    form_name, field_map, data, attorney_info, beneficiary_name
                )

            logger.info(f"Filled {form_name}: {filled_count}/{total_in_map} fields via pdftk, "
                        f"resolved={len(fdf_fields)}, unresolved={len(unresolved)}")

            return output_path, {
                "success": True,
                "method": "pdftk_fill",
                "filled_fields": filled_count,
                "pdf_fields_set": len(fdf_fields),
                "unresolved_fields": len(unresolved),
                "skipped_fields": skipped_count,
                "total_mapped": total_in_map,
                "fill_pct": round(filled_count / total_in_map * 100) if total_in_map > 0 else 0,
            }

        except FileNotFoundError:
            logger.error("pdftk not installed - cannot fill PDF forms")
            return self._generate_summary_pdf(
                form_name, field_map, data, attorney_info, beneficiary_name
            )
        except Exception as e:
            logger.error(f"pdftk fill error for {form_name}: {e}", exc_info=True)
            return self._generate_summary_pdf(
                form_name, field_map, data, attorney_info, beneficiary_name
            )

    def _generate_summary_pdf(
        self,
        form_name: str,
        field_map: Dict[str, str],
        data: Dict,
        attorney_info: Dict,
        beneficiary_name: str,
    ) -> Tuple[Optional[str], Dict]:
        """Generate a summary PDF showing filled data (fallback when no fillable PDF)."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.lib.colors import HexColor

            safe_name = "".join(c for c in beneficiary_name if c.isalnum() or c in " _-")[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"FormData_{form_name}_{safe_name}_{timestamp}.pdf"
            output_path = os.path.join(OUTPUT_DIR, filename)

            c = canvas.Canvas(output_path, pagesize=letter)
            width, height = letter

            # Header
            c.setFont("Helvetica-Bold", 16)
            c.drawString(1 * inch, height - 1 * inch, f"USCIS {form_name} — Form Data Summary")
            c.setFont("Helvetica", 10)
            c.setFillColor(HexColor("#666666"))
            c.drawString(1 * inch, height - 1.3 * inch, f"Beneficiary: {beneficiary_name}")
            c.drawString(1 * inch, height - 1.5 * inch, f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
            c.drawString(1 * inch, height - 1.7 * inch,
                         "Note: Official USCIS fillable PDF not available. This is a data summary.")
            c.setFillColor(HexColor("#000000"))

            # Separator
            c.setStrokeColor(HexColor("#cccccc"))
            c.line(1 * inch, height - 1.9 * inch, width - 1 * inch, height - 1.9 * inch)

            y = height - 2.2 * inch
            filled_count = 0

            # Group fields by section (part)
            current_section = ""
            for our_field in sorted(field_map.keys()):
                value = data.get(our_field, "")
                if not value or not str(value).strip():
                    continue

                # Extract section from field name (p1_ -> Part 1, p2_ -> Part 2, etc.)
                section = our_field.split("_")[0] if "_" in our_field else ""
                section_label = f"Part {section[1:]}" if section.startswith("p") and len(section) > 1 else section

                if section_label != current_section:
                    current_section = section_label
                    if y < 1.5 * inch:
                        c.showPage()
                        y = height - 1 * inch
                    c.setFont("Helvetica-Bold", 11)
                    c.setFillColor(HexColor("#1a1a2e"))
                    c.drawString(1 * inch, y, current_section)
                    c.setFillColor(HexColor("#000000"))
                    y -= 0.25 * inch

                if y < 1 * inch:
                    c.showPage()
                    y = height - 1 * inch

                # Field label and value
                label = our_field.replace("_", " ").title()
                c.setFont("Helvetica", 9)
                c.setFillColor(HexColor("#555555"))
                c.drawString(1.2 * inch, y, f"{label}:")
                c.setFillColor(HexColor("#000000"))
                c.setFont("Helvetica-Bold", 9)

                # Truncate long values
                str_val = str(value)[:80]
                c.drawString(3.5 * inch, y, str_val)
                y -= 0.2 * inch
                filled_count += 1

            c.save()

            return output_path, {
                "success": True,
                "method": "summary_pdf",
                "filled_fields": filled_count,
                "total_mapped": len(field_map),
                "fill_pct": round(filled_count / len(field_map) * 100) if field_map else 0,
                "note": "Summary PDF generated (official fillable PDF not available)",
            }

        except Exception as e:
            logger.error(f"Summary PDF generation error: {e}", exc_info=True)
            return None, {"error": str(e), "success": False}

    def _format_value(self, field_name: str, value) -> str:
        """Format a value for PDF field filling."""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        str_val = str(value).strip()
        # Format dates: if field name suggests a date
        if "date" in field_name.lower() or "dob" in field_name.lower():
            # Try to normalize date format to mm/dd/yyyy
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"]:
                try:
                    dt = datetime.strptime(str_val, fmt)
                    return dt.strftime("%m/%d/%Y")
                except ValueError:
                    continue
        return str_val


# Singleton instance
form_filler = FormFillerService()
