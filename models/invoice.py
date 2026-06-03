"""
CaseHub - Invoice Model
Track invoices separately from billing items for better management.
"""
from sqlalchemy import Column, Integer, String, Date, Text, DateTime, ForeignKey, Numeric, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)

    # Invoice details
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date)
    status = Column(String(20), default="draft")  # draft, sent, paid, overdue, cancelled

    # Amounts
    subtotal = Column(Numeric(10, 2), default=0)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    discount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)
    amount_paid = Column(Numeric(10, 2), default=0)
    balance_due = Column(Numeric(10, 2), default=0)

    # Payment info
    paid_date = Column(Date)
    payment_method = Column(String(50))
    payment_reference = Column(String(100))

    # Metadata
    notes = Column(Text)
    terms = Column(Text)  # Payment terms
    footer = Column(Text)  # Custom footer text

    # Tracking
    sent_at = Column(DateTime)
    sent_to = Column(String(200))  # Email address(es) sent to
    last_reminder = Column(DateTime)
    reminder_count = Column(Integer, default=0)

    # PDF storage
    pdf_path = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    # items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)

    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)

    # Link to original billing item if applicable
    billing_item_id = Column(Integer, ForeignKey("billing_items.id"))
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"))

    item_type = Column(String(50))  # fee, expense, time, filing_fee
    taxable = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    # invoice = relationship("Invoice", back_populates="items")


# SQL to create the invoices tables
CREATE_INVOICES_TABLE = """
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE,
    status VARCHAR(20) DEFAULT 'draft',
    subtotal DECIMAL(10,2) DEFAULT 0,
    tax_rate DECIMAL(5,2) DEFAULT 0,
    tax_amount DECIMAL(10,2) DEFAULT 0,
    discount DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) DEFAULT 0,
    amount_paid DECIMAL(10,2) DEFAULT 0,
    balance_due DECIMAL(10,2) DEFAULT 0,
    paid_date DATE,
    payment_method VARCHAR(50),
    payment_reference VARCHAR(100),
    notes TEXT,
    terms TEXT,
    footer TEXT,
    sent_at TIMESTAMP,
    sent_to VARCHAR(200),
    last_reminder TIMESTAMP,
    reminder_count INTEGER DEFAULT 0,
    pdf_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_client ON invoices(client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);

CREATE TABLE IF NOT EXISTS invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE NOT NULL,
    description VARCHAR(500) NOT NULL,
    quantity DECIMAL(10,2) DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    billing_item_id INTEGER REFERENCES billing_items(id),
    time_entry_id INTEGER REFERENCES time_entries(id),
    item_type VARCHAR(50),
    taxable BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id);
"""
