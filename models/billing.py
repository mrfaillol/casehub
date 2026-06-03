"""
CaseHub - Billing Models
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base

class BillingItem(Base):
    __tablename__ = "billing_items"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    item_type = Column(String(50))  # fee, filing_fee, expense, payment
    status = Column(String(50), default="pending")  # pending, invoiced, paid
    invoice_number = Column(String(50), index=True, nullable=True)
    due_date = Column(Date)
    paid_date = Column(Date)
    notes = Column(Text)
    currency = Column(String(3), default="USD")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    case = relationship("Case", backref="billing_items")


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    description = Column(Text, nullable=False)
    hours = Column(Numeric(5, 2), nullable=False)
    rate = Column(Numeric(10, 2))
    date = Column(Date, nullable=False)
    billable = Column(Boolean, default=True)
    currency = Column(String(3), default="USD")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    case = relationship("Case", backref="time_entries")
    user = relationship("User", backref="time_entries")
