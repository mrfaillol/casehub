"""
CaseHub - Shipment Tracking Service
Track USPS, FedEx, UPS shipments for cases.
"""
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import json


class Carrier(str, Enum):
    USPS = "usps"
    FEDEX = "fedex"
    UPS = "ups"
    DHL = "dhl"
    OTHER = "other"


class ShipmentStatus(str, Enum):
    LABEL_CREATED = "label_created"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXCEPTION = "exception"
    RETURNED = "returned"


class ShipmentService:
    """Service for tracking shipments."""

    # Carrier tracking URL patterns
    TRACKING_URLS = {
        Carrier.USPS: "https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
        Carrier.FEDEX: "https://www.fedex.com/fedextrack/?trknbr={tracking}",
        Carrier.UPS: "https://www.ups.com/track?tracknum={tracking}",
        Carrier.DHL: "https://www.dhl.com/us-en/home/tracking/tracking-express.html?submit=1&tracking-id={tracking}"
    }

    def detect_carrier(self, tracking_number: str) -> Optional[str]:
        """Detect carrier from tracking number format."""
        tracking = tracking_number.strip().upper()

        # USPS patterns
        if len(tracking) == 22 and tracking.isdigit():
            return Carrier.USPS
        if len(tracking) == 20 and tracking.startswith("94"):
            return Carrier.USPS

        # FedEx patterns
        if len(tracking) in [12, 15, 20, 22]:
            if tracking.isdigit():
                return Carrier.FEDEX

        # UPS patterns
        if tracking.startswith("1Z"):
            return Carrier.UPS

        # DHL patterns
        if len(tracking) == 10 and tracking.isdigit():
            return Carrier.DHL

        return Carrier.OTHER

    def get_tracking_url(self, carrier: str, tracking_number: str) -> str:
        """Get tracking URL for a shipment."""
        url_template = self.TRACKING_URLS.get(carrier, "")
        if url_template:
            return url_template.format(tracking=tracking_number)
        return ""

    def create_shipment(
        self,
        db_session,
        case_id: int,
        tracking_number: str,
        carrier: str = None,
        direction: str = "outbound",
        recipient: str = None,
        description: str = None,
        user_id: int = None
    ) -> Dict:
        """Create a new shipment record."""
        from sqlalchemy import text
        import uuid

        shipment_id = str(uuid.uuid4())[:8]

        # Auto-detect carrier if not provided
        if not carrier:
            carrier = self.detect_carrier(tracking_number)

        try:
            db_session.execute(text("""
                INSERT INTO shipments
                (shipment_id, case_id, tracking_number, carrier, direction, recipient, description, status, created_by)
                VALUES (:sid, :cid, :tracking, :carrier, :direction, :recipient, :desc, :status, :uid)
            """), {
                "sid": shipment_id,
                "cid": case_id,
                "tracking": tracking_number.strip().upper(),
                "carrier": carrier,
                "direction": direction,
                "recipient": recipient,
                "desc": description,
                "status": ShipmentStatus.LABEL_CREATED,
                "uid": user_id
            })
            db_session.commit()

            return {"success": True, "shipment_id": shipment_id}
        except Exception as e:
            db_session.rollback()
            return {"success": False, "error": str(e)}

    def update_status(self, db_session, shipment_id: str, status: str, location: str = None) -> Dict:
        """Update shipment status."""
        from sqlalchemy import text

        try:
            params = {"sid": shipment_id, "status": status, "location": location}

            if status == ShipmentStatus.DELIVERED:
                db_session.execute(text("""
                    UPDATE shipments
                    SET status = :status, updated_at = NOW(),
                        last_location = COALESCE(:location, last_location),
                        delivered_at = NOW()
                    WHERE shipment_id = :sid
                """), params)
            else:
                db_session.execute(text("""
                    UPDATE shipments
                    SET status = :status, updated_at = NOW(),
                        last_location = COALESCE(:location, last_location)
                    WHERE shipment_id = :sid
                """), params)
            db_session.commit()

            return {"success": True}
        except Exception as e:
            db_session.rollback()
            return {"success": False, "error": str(e)}

    def get_shipments_for_case(self, db_session, case_id: int) -> List[Dict]:
        """Get all shipments for a case."""
        from sqlalchemy import text

        try:
            result = db_session.execute(text("""
                SELECT * FROM shipments
                WHERE case_id = :cid
                ORDER BY created_at DESC
            """), {"cid": case_id})

            shipments = []
            for row in result.fetchall():
                shipment = dict(row._mapping)
                shipment["tracking_url"] = self.get_tracking_url(
                    shipment["carrier"],
                    shipment["tracking_number"]
                )
                shipments.append(shipment)

            return shipments
        except Exception:
            return []

    def get_all_shipments(self, db_session, status: str = None) -> List[Dict]:
        """Get all shipments with optional status filter."""
        from sqlalchemy import text

        query = """
            SELECT s.*, c.case_number, c.case_name,
                   cl.first_name, cl.last_name
            FROM shipments s
            LEFT JOIN cases c ON s.case_id = c.id
            LEFT JOIN clients cl ON c.client_id = cl.id
        """
        params = {}

        if status:
            query += " WHERE s.status = :status"
            params["status"] = status

        query += " ORDER BY s.created_at DESC"

        try:
            result = db_session.execute(text(query), params)

            shipments = []
            for row in result.fetchall():
                shipment = dict(row._mapping)
                shipment["tracking_url"] = self.get_tracking_url(
                    shipment["carrier"],
                    shipment["tracking_number"]
                )
                shipments.append(shipment)

            return shipments
        except Exception:
            return []

    def get_pending_shipments(self, db_session) -> List[Dict]:
        """Get shipments that haven't been delivered yet."""
        return self.get_all_shipments(db_session, None)


# SQL for shipments table
CREATE_SHIPMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS shipments (
    id SERIAL PRIMARY KEY,
    shipment_id VARCHAR(20) UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id),
    tracking_number VARCHAR(100) NOT NULL,
    carrier VARCHAR(20) NOT NULL,
    direction VARCHAR(20) DEFAULT 'outbound',
    status VARCHAR(50) DEFAULT 'label_created',
    recipient VARCHAR(200),
    description TEXT,
    last_location VARCHAR(200),
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_shipments_case ON shipments(case_id);
CREATE INDEX IF NOT EXISTS idx_shipments_tracking ON shipments(tracking_number);
CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
"""


# Singleton instance
shipment_service = ShipmentService()
