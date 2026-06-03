"""Collect (inbound, field_request, admin_resolve) tuples into MaestroTrainingSample rows.

Called from:
  - services/whatsapp_inbound_service.py.seed_training_sample_if_enabled
    (seeds an awaiting_admin row when consent + flag agree)
  - routes/whatsapp_inbound.py.resolve_field_request
    (updates the corresponding sample with admin-validated value)

Both paths are no-ops unless settings.MAESTRO_TRAINING_COLLECTION_ENABLED is True.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.whatsapp_inbound import MaestroTrainingSample


logger = logging.getLogger(__name__)


def attach_admin_resolve(
    db: Session,
    *,
    field_request_id: int,
    resolved_value: str,
    user_id: int,
    is_correct_label: bool = True,
) -> Optional[int]:
    """Find the sample seeded for this field_request and write the labelled extracted_value.

    Returns updated sample.id or None if none was seeded.
    """
    if not getattr(settings, "MAESTRO_TRAINING_COLLECTION_ENABLED", False):
        return None

    sample = (
        db.query(MaestroTrainingSample)
        .filter(MaestroTrainingSample.source_field_request_id == field_request_id)
        .first()
    )
    if not sample:
        return None

    sample.extracted_value = (resolved_value or "")[:4000]
    sample.validated_by_user_id = user_id
    sample.validated_at = datetime.now(tz=timezone.utc)
    sample.is_correct_label = is_correct_label
    sample.label_provenance = "admin_resolve" if is_correct_label else "admin_correct"
    db.commit()
    return sample.id
