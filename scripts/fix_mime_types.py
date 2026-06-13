#!/usr/bin/env python3
import sys
from pathlib import Path
import mimetypes
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.base import get_db
from models.document import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = next(get_db())

# Get documents with None mime_type
docs = db.query(Document).filter(Document.mime_type == None).all()
logger.info(f"Found {len(docs)} documents with None mime_type")

fixed = 0
for doc in docs:
    file_path = Path(doc.file_path or doc.storage_path or "")
    if file_path.suffix:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            doc.mime_type = mime_type
            fixed += 1

if fixed > 0:
    db.commit()
    logger.info(f"✅ Fixed {fixed} MIME types")
else:
    logger.info("No MIME types could be inferred from file extensions")

db.close()
