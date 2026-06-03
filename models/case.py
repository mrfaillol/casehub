"""
CaseHub - Case Model
"""
from sqlalchemy import Column, Integer, String, Date, Text, DateTime, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    case_number = Column(String(50), unique=True, index=True)
    receipt_number = Column(String(50), index=True)
    case_name = Column(String(200))
    visa_type = Column(String(100))
    status = Column(String(50), default="intake")
    priority = Column(String(20), default="medium")
    area_of_practice = Column(String(100))
    # === Brazilian Law (Lite product) ===
    numero_processo = Column(String(50), index=True)  # Brazilian court process number
    tipo_acao = Column(String(100))  # Type of lawsuit
    vara = Column(String(100))  # Court division
    comarca = Column(String(100))  # Court district
    tribunal = Column(String(100))  # Court name (TJMG, TRF, etc.)
    fase_processual = Column(String(100))  # Procedural phase
    polo_ativo = Column(Text)  # Plaintiff/active party
    polo_passivo = Column(Text)  # Defendant/passive party
    jurisdiction = Column(String(100))
    filing_date = Column(Date)
    priority_date = Column(Date)
    expiration_date = Column(Date)
    case_value = Column(Numeric(10, 2))
    amount_paid = Column(Numeric(10, 2))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    client = relationship("Client", back_populates="cases")
    documents = relationship("Document", back_populates="case")
