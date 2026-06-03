"""
CaseHub - Client Model
"""
from sqlalchemy import Column, Integer, String, Date, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))
    last_name = Column(String(100), nullable=False)
    email = Column(String(200), index=True)
    phone = Column(String(50))
    whatsapp = Column(String(50))
    date_of_birth = Column(Date)
    country_of_origin = Column(String(100))
    # PII fields -- stored encrypted via Fernet (see services/encryption.py)
    ssn = Column(String(200))  # Encrypted; was String(20)
    alien_number = Column(String(200))  # Encrypted; was String(50)
    client_number = Column(String(50), index=True)
    passport_number = Column(String(200))  # Encrypted; was String(50)
    # === Brazilian Law (Lite product) ===
    cpf = Column(String(200))  # Encrypted; Brazilian tax ID
    rg = Column(String(200))  # Encrypted; Brazilian ID card
    cnpj = Column(String(200))  # Encrypted; Company tax ID
    oab_number = Column(String(50))  # OAB registration
    nationality = Column(String(100))  # Generic (replaces country_of_origin for Lite)
    client_type = Column(String(20), default="individual")  # "individual" or "corporate"
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    status = Column(String(50), default="active")
    notes = Column(Text)
    drive_folder_id = Column(String(200))
    drive_folder_name = Column(String(300))
    tasks_folder_data = Column(Text)  # JSON: [{"id": "xxx", "name": "...", "paralegal": "Juliana", "archived": false}]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    cases = relationship("Case", back_populates="client")
    documents = relationship("Document", back_populates="client")

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    def encrypt_pii(self):
        """Encrypt PII fields before saving to database."""
        from services.encryption import encrypt_value
        if self.ssn:
            self.ssn = encrypt_value(self.ssn)
        if self.alien_number:
            self.alien_number = encrypt_value(self.alien_number)
        if self.passport_number:
            self.passport_number = encrypt_value(self.passport_number)
        # Brazilian PII
        if self.cpf:
            self.cpf = encrypt_value(self.cpf)
        if self.rg:
            self.rg = encrypt_value(self.rg)
        if self.cnpj:
            self.cnpj = encrypt_value(self.cnpj)

    def decrypt_pii(self):
        """Decrypt PII fields after reading from database."""
        from services.encryption import decrypt_value
        if self.ssn:
            self.ssn = decrypt_value(self.ssn)
        if self.alien_number:
            self.alien_number = decrypt_value(self.alien_number)
        if self.passport_number:
            self.passport_number = decrypt_value(self.passport_number)
        # Brazilian PII
        if self.cpf:
            self.cpf = decrypt_value(self.cpf)
        if self.rg:
            self.rg = decrypt_value(self.rg)
        if self.cnpj:
            self.cnpj = decrypt_value(self.cnpj)

    @property
    def decrypted_ssn(self):
        """Return decrypted SSN without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.ssn) if self.ssn else None

    @property
    def decrypted_alien_number(self):
        """Return decrypted alien_number without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.alien_number) if self.alien_number else None

    @property
    def decrypted_passport_number(self):
        """Return decrypted passport_number without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.passport_number) if self.passport_number else None

    @property
    def decrypted_cpf(self):
        """Return decrypted CPF without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.cpf) if self.cpf else None

    @property
    def decrypted_rg(self):
        """Return decrypted RG without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.rg) if self.rg else None

    @property
    def decrypted_cnpj(self):
        """Return decrypted CNPJ without modifying the instance."""
        from services.encryption import decrypt_value
        return decrypt_value(self.cnpj) if self.cnpj else None
