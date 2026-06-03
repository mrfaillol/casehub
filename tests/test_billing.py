"""
Tests for models.billing - BillingItem and TimeEntry models with currency support.
"""
import pytest
from decimal import Decimal
from datetime import date

from models.billing import BillingItem, TimeEntry
from models.case import Case
from models.client import Client


class TestBillingItemModel:
    """Tests for the BillingItem SQLAlchemy model."""

    def _create_case(self, db):
        """Helper: create a minimal client + case for foreign key."""
        client = Client(first_name="Test", last_name="Client")
        db.add(client)
        db.flush()
        case = Case(client_id=client.id, case_number="CH-001")
        db.add(case)
        db.flush()
        return case

    def test_billing_item_has_currency_field(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="Filing fee",
            amount=Decimal("500.00"),
        )
        db.add(item)
        db.flush()

        assert hasattr(item, "currency")

    def test_billing_item_default_currency_is_usd(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="Consultation",
            amount=Decimal("200.00"),
        )
        db.add(item)
        db.flush()

        assert item.currency == "USD"

    def test_billing_item_with_brl_currency(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="Honorarios advocaticios",
            amount=Decimal("3500.00"),
            currency="BRL",
        )
        db.add(item)
        db.flush()

        assert item.currency == "BRL"
        assert item.amount == Decimal("3500.00")

    def test_billing_item_with_eur_currency(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="EU filing",
            amount=Decimal("750.00"),
            currency="EUR",
        )
        db.add(item)
        db.flush()

        assert item.currency == "EUR"

    def test_billing_item_status_default_pending(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="Payment",
            amount=Decimal("100.00"),
        )
        db.add(item)
        db.flush()

        assert item.status == "pending"

    def test_billing_item_types(self, db):
        case = self._create_case(db)
        for item_type in ["fee", "filing_fee", "expense", "payment"]:
            item = BillingItem(
                case_id=case.id,
                description=f"Type {item_type}",
                amount=Decimal("100.00"),
                item_type=item_type,
            )
            db.add(item)
            db.flush()
            assert item.item_type == item_type

    def test_billing_item_case_relationship(self, db):
        case = self._create_case(db)
        item = BillingItem(
            case_id=case.id,
            description="Linked to case",
            amount=Decimal("100.00"),
        )
        db.add(item)
        db.flush()
        db.refresh(item)

        assert item.case is not None
        assert item.case.id == case.id


class TestTimeEntryModel:
    """Tests for the TimeEntry SQLAlchemy model."""

    def _create_case(self, db):
        """Helper: create a minimal client + case for foreign key."""
        client = Client(first_name="Time", last_name="User")
        db.add(client)
        db.flush()
        case = Case(client_id=client.id, case_number="CH-TE-001")
        db.add(case)
        db.flush()
        return case

    def test_time_entry_has_currency_field(self, db):
        case = self._create_case(db)
        entry = TimeEntry(
            case_id=case.id,
            description="Research case law",
            hours=Decimal("2.50"),
            date=date(2026, 3, 25),
        )
        db.add(entry)
        db.flush()

        assert hasattr(entry, "currency")

    def test_time_entry_default_currency_is_usd(self, db):
        case = self._create_case(db)
        entry = TimeEntry(
            case_id=case.id,
            description="Client call",
            hours=Decimal("0.50"),
            date=date(2026, 3, 25),
        )
        db.add(entry)
        db.flush()

        assert entry.currency == "USD"

    def test_time_entry_with_brl_currency(self, db):
        case = self._create_case(db)
        entry = TimeEntry(
            case_id=case.id,
            description="Audiencia",
            hours=Decimal("3.00"),
            rate=Decimal("250.00"),
            date=date(2026, 3, 25),
            currency="BRL",
        )
        db.add(entry)
        db.flush()

        assert entry.currency == "BRL"

    def test_time_entry_billable_default_true(self, db):
        case = self._create_case(db)
        entry = TimeEntry(
            case_id=case.id,
            description="Billable by default",
            hours=Decimal("1.00"),
            date=date(2026, 3, 25),
        )
        db.add(entry)
        db.flush()

        assert entry.billable is True

    def test_time_entry_non_billable(self, db):
        case = self._create_case(db)
        entry = TimeEntry(
            case_id=case.id,
            description="Internal review",
            hours=Decimal("1.00"),
            date=date(2026, 3, 25),
            billable=False,
        )
        db.add(entry)
        db.flush()

        assert entry.billable is False
