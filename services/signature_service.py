"""
CaseHub - Electronic Signature Service
Handle signature capture, storage, and application to documents.
"""
import os
import base64
import hashlib
import json
from datetime import datetime
from io import BytesIO
from typing import Optional
import uuid

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class SignatureService:
    """Service for electronic signature management."""

    UPLOAD_DIR = "uploads/signatures"

    def __init__(self):
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)

    def save_drawn_signature(self, user_id: int, signature_data: str, name: str = None) -> dict:
        """Save a signature drawn on canvas.

        Args:
            user_id: ID of the user
            signature_data: Base64 encoded PNG data (data:image/png;base64,...)
            name: Optional name for the signature

        Returns:
            Dictionary with signature info
        """
        try:
            # Remove data URL prefix if present
            if ',' in signature_data:
                signature_data = signature_data.split(',')[1]

            # Decode base64
            image_data = base64.b64decode(signature_data)

            # Generate unique filename
            sig_id = str(uuid.uuid4())[:8]
            filename = f"sig_{user_id}_{sig_id}.png"
            filepath = os.path.join(self.UPLOAD_DIR, filename)

            # Save image
            with open(filepath, 'wb') as f:
                f.write(image_data)

            # Generate checksum for verification
            checksum = hashlib.sha256(image_data).hexdigest()

            return {
                "success": True,
                "signature_id": sig_id,
                "filepath": filepath,
                "filename": filename,
                "checksum": checksum,
                "type": "drawn",
                "name": name,
                "created_at": datetime.now().isoformat()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_uploaded_signature(self, user_id: int, file_data: bytes, filename: str, name: str = None) -> dict:
        """Save an uploaded signature image.

        Args:
            user_id: ID of the user
            file_data: Image file bytes
            filename: Original filename
            name: Optional name for the signature

        Returns:
            Dictionary with signature info
        """
        try:
            # Get file extension
            ext = filename.rsplit('.', 1)[-1].lower()
            if ext not in ['png', 'jpg', 'jpeg', 'gif']:
                return {"success": False, "error": "Invalid file type. Use PNG, JPG, or GIF."}

            # Generate unique filename
            sig_id = str(uuid.uuid4())[:8]
            new_filename = f"sig_{user_id}_{sig_id}.{ext}"
            filepath = os.path.join(self.UPLOAD_DIR, new_filename)

            # Save file
            with open(filepath, 'wb') as f:
                f.write(file_data)

            # Generate checksum
            checksum = hashlib.sha256(file_data).hexdigest()

            return {
                "success": True,
                "signature_id": sig_id,
                "filepath": filepath,
                "filename": new_filename,
                "checksum": checksum,
                "type": "uploaded",
                "name": name,
                "created_at": datetime.now().isoformat()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def generate_typed_signature(self, user_id: int, text: str, font_style: str = "cursive", name: str = None) -> dict:
        """Generate a signature image from typed text.

        Args:
            user_id: ID of the user
            text: Text to convert to signature
            font_style: Style of font (cursive, formal, casual)
            name: Optional name for the signature

        Returns:
            Dictionary with signature info
        """
        if not PIL_AVAILABLE:
            return {"success": False, "error": "PIL not available for image generation"}

        try:
            # Create signature image
            width, height = 400, 100
            image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)

            # Try to load a nice font, fallback to default
            try:
                # Try common cursive fonts
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
                    "/System/Library/Fonts/MarkerFelt.ttc",
                    "/Library/Fonts/Brush Script.ttc"
                ]
                font = None
                for path in font_paths:
                    if os.path.exists(path):
                        font = ImageFont.truetype(path, 48)
                        break
                if not font:
                    font = ImageFont.load_default()
            except (OSError, IOError):
                font = ImageFont.load_default()

            # Calculate text position to center it
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2

            # Draw text in dark blue (more signature-like)
            draw.text((x, y), text, fill=(0, 0, 139), font=font)

            # Save to file
            sig_id = str(uuid.uuid4())[:8]
            filename = f"sig_{user_id}_{sig_id}.png"
            filepath = os.path.join(self.UPLOAD_DIR, filename)

            image.save(filepath, 'PNG')

            # Read back for checksum
            with open(filepath, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()

            return {
                "success": True,
                "signature_id": sig_id,
                "filepath": filepath,
                "filename": filename,
                "checksum": checksum,
                "type": "typed",
                "text": text,
                "font_style": font_style,
                "name": name,
                "created_at": datetime.now().isoformat()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_signature(self, filepath: str) -> bool:
        """Delete a signature file.

        Args:
            filepath: Path to the signature file

        Returns:
            True if deleted successfully
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            return False
        except OSError:
            return False

    def get_signature_as_base64(self, filepath: str) -> Optional[str]:
        """Get signature as base64 encoded string for embedding.

        Args:
            filepath: Path to the signature file

        Returns:
            Base64 encoded image string or None
        """
        try:
            if not os.path.exists(filepath):
                return None

            with open(filepath, 'rb') as f:
                data = f.read()

            # Determine mime type
            ext = filepath.rsplit('.', 1)[-1].lower()
            mime_types = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif'
            }
            mime = mime_types.get(ext, 'image/png')

            return f"data:{mime};base64,{base64.b64encode(data).decode()}"

        except (OSError, IOError):
            return None

    def create_signature_record(self, signature_data: dict, ip_address: str = None, user_agent: str = None) -> dict:
        """Create a signature audit record.

        Args:
            signature_data: Signature info from save methods
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Complete signature record with audit info
        """
        return {
            **signature_data,
            "audit": {
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
                "timezone": "UTC"
            }
        }


# SQL for signatures table
CREATE_SIGNATURES_TABLE = """
CREATE TABLE IF NOT EXISTS signatures (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    name VARCHAR(100),
    type VARCHAR(20) NOT NULL,  -- 'drawn', 'uploaded', 'typed'
    filepath VARCHAR(500) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    is_default BOOLEAN DEFAULT false,
    typed_text VARCHAR(200),
    font_style VARCHAR(50),
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signatures_user ON signatures(user_id);

CREATE TABLE IF NOT EXISTS signature_applications (
    id SERIAL PRIMARY KEY,
    signature_id INTEGER REFERENCES signatures(id) NOT NULL,
    document_id INTEGER REFERENCES documents(id),
    applied_by INTEGER REFERENCES users(id) NOT NULL,
    purpose VARCHAR(200),
    document_hash VARCHAR(64),
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signature_apps_sig ON signature_applications(signature_id);
CREATE INDEX IF NOT EXISTS idx_signature_apps_doc ON signature_applications(document_id);
"""


# Singleton instance
signature_service = SignatureService()
