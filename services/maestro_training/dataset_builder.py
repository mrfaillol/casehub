"""Export validated training samples to JSONL files for offline training.

Default: writes to data/maestro_training/<field_name>.jsonl. Refuses to run if collection
flag is off. Refuses to include samples without consent_recorded == True.

This is a build-time tool — not invoked from the request lifecycle.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from config import settings
from models.whatsapp_inbound import MaestroTrainingSample


logger = logging.getLogger(__name__)

DEFAULT_OUT_DIR = Path("data/maestro_training")


def iter_eligible(db: Session, field_name: Optional[str] = None) -> Iterable[MaestroTrainingSample]:
    q = (
        db.query(MaestroTrainingSample)
        .filter(MaestroTrainingSample.consent_recorded.is_(True))
        .filter(MaestroTrainingSample.is_correct_label.is_(True))
    )
    if field_name:
        q = q.filter(MaestroTrainingSample.source_field_name == field_name)
    return q.yield_per(500)


def export_jsonl(db: Session, field_name: str, out_dir: Path = DEFAULT_OUT_DIR) -> int:
    if not getattr(settings, "MAESTRO_TRAINING_COLLECTION_ENABLED", False):
        raise RuntimeError(
            "MAESTRO_TRAINING_COLLECTION_ENABLED is off; refusing to export. "
            "Council ruling required before activating."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{field_name}.jsonl"

    count = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for sample in iter_eligible(db, field_name=field_name):
            row = {
                "id": sample.id,
                "raw_message": sample.raw_message,
                "extracted_value": sample.extracted_value,
                "field_name": sample.source_field_name,
                "consent_provider": sample.consent_provider,
                "label_provenance": sample.label_provenance,
            }
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    logger.info("exported %d samples for field=%s to %s", count, field_name, out_path)
    return count
