#!/usr/bin/env python3
"""
Download official USCIS fillable PDF forms for the FormFillerService.
Forms are stored in data/uscis_forms/ directory.

Usage:
    python3 scripts/download_uscis_pdfs.py
    python3 scripts/download_uscis_pdfs.py --form G-28
"""
import os
import sys
import urllib.request
import ssl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "uscis_forms")

# USCIS standard form download URLs
# These are publicly available at uscis.gov
FORM_URLS = {
    "g-28": "https://www.uscis.gov/sites/default/files/document/forms/g-28.pdf",
    "i-130": "https://www.uscis.gov/sites/default/files/document/forms/i-130.pdf",
    "i-130a": "https://www.uscis.gov/sites/default/files/document/forms/i-130a.pdf",
    "i-131": "https://www.uscis.gov/sites/default/files/document/forms/i-131.pdf",
    "i-140": "https://www.uscis.gov/sites/default/files/document/forms/i-140.pdf",
    "i-485": "https://www.uscis.gov/sites/default/files/document/forms/i-485.pdf",
    "i-765": "https://www.uscis.gov/sites/default/files/document/forms/i-765.pdf",
    "i-864": "https://www.uscis.gov/sites/default/files/document/forms/i-864.pdf",
    "i-907": "https://www.uscis.gov/sites/default/files/document/forms/i-907.pdf",
    "i-129": "https://www.uscis.gov/sites/default/files/document/forms/i-129.pdf",
}


def download_form(form_name: str, url: str) -> bool:
    """Download a single USCIS form PDF."""
    output_path = os.path.join(OUTPUT_DIR, f"{form_name}.pdf")

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        if size > 10000:  # Minimum 10KB for a valid PDF
            print(f"  [SKIP] {form_name}.pdf already exists ({size:,} bytes)")
            return True

    print(f"  [DOWNLOAD] {form_name}.pdf from {url}")
    try:
        # Create SSL context that doesn't verify (some servers have cert issues)
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ILC CaseHub/1.0; +https://immigrant.law)"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            data = response.read()
            if len(data) < 1000:
                print(f"  [FAIL] {form_name}.pdf — response too small ({len(data)} bytes)")
                return False
            with open(output_path, "wb") as f:
                f.write(data)
            print(f"  [OK] {form_name}.pdf ({len(data):,} bytes)")
            return True
    except Exception as e:
        print(f"  [FAIL] {form_name}.pdf — {e}")
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Filter to specific form if requested
    specific_form = None
    if len(sys.argv) > 1 and sys.argv[1] == "--form" and len(sys.argv) > 2:
        specific_form = sys.argv[2].lower()

    print(f"USCIS PDF Download Script")
    print(f"Output: {OUTPUT_DIR}")
    print()

    success = 0
    failed = 0

    for form_name, url in sorted(FORM_URLS.items()):
        if specific_form and form_name != specific_form:
            continue
        if download_form(form_name, url):
            success += 1
        else:
            failed += 1

    print(f"\nResults: {success} OK, {failed} failed")

    # Verify downloaded PDFs are valid
    print("\nVerification:")
    for form_name in sorted(FORM_URLS.keys()):
        if specific_form and form_name != specific_form:
            continue
        path = os.path.join(OUTPUT_DIR, f"{form_name}.pdf")
        if os.path.exists(path):
            size = os.path.getsize(path)
            try:
                with open(path, "rb") as f:
                    header = f.read(5)
                is_pdf = header == b"%PDF-"
                status = "valid PDF" if is_pdf else "NOT a PDF!"
            except Exception:
                status = "read error"
            print(f"  {form_name}.pdf: {size:,} bytes — {status}")
        else:
            print(f"  {form_name}.pdf: MISSING")


if __name__ == "__main__":
    main()
