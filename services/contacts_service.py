"""
CaseHub - Contacts/Member Linking Service
Manage relationships between clients, employers, and other contacts.
"""
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum


class ContactType(str, Enum):
    EMPLOYER = "employer"
    EMPLOYEE = "employee"
    SPOUSE = "spouse"
    PARENT = "parent"
    CHILD = "child"
    ATTORNEY = "attorney"
    PETITIONER = "petitioner"
    BENEFICIARY = "beneficiary"
    REFERENCE = "reference"
    EXPERT_WITNESS = "expert_witness"
    OTHER = "other"


class RelationshipType(str, Enum):
    EMPLOYMENT = "employment"
    FAMILY = "family"
    LEGAL = "legal"
    REFERENCE = "reference"
    OTHER = "other"


class ContactsService:
    """Service for managing contacts and relationships."""

    # Relationship mappings (bidirectional)
    RELATIONSHIP_PAIRS = {
        "employer": "employee",
        "employee": "employer",
        "spouse": "spouse",
        "parent": "child",
        "child": "parent",
        "attorney": "client",
        "client": "attorney",
        "petitioner": "beneficiary",
        "beneficiary": "petitioner"
    }

    # Relationship categories
    RELATIONSHIP_CATEGORIES = {
        RelationshipType.EMPLOYMENT: ["employer", "employee"],
        RelationshipType.FAMILY: ["spouse", "parent", "child"],
        RelationshipType.LEGAL: ["attorney", "client", "petitioner", "beneficiary"],
        RelationshipType.REFERENCE: ["reference", "expert_witness"],
    }

    def get_inverse_relationship(self, relationship: str) -> str:
        """Get the inverse of a relationship."""
        return self.RELATIONSHIP_PAIRS.get(relationship, "related")

    def get_relationship_category(self, relationship: str) -> str:
        """Get the category of a relationship."""
        for category, relationships in self.RELATIONSHIP_CATEGORIES.items():
            if relationship in relationships:
                return category.value
        return RelationshipType.OTHER.value

    def create_contact(
        self,
        contact_type: str,
        name: str,
        company: str = None,
        title: str = None,
        email: str = None,
        phone: str = None,
        address: str = None,
        notes: str = None
    ) -> dict:
        """Create a new contact record."""
        return {
            "contact_type": contact_type,
            "name": name,
            "company": company,
            "title": title,
            "email": email,
            "phone": phone,
            "address": address,
            "notes": notes,
            "created_at": datetime.now()
        }

    def create_relationship(
        self,
        from_id: int,
        from_type: str,
        to_id: int,
        to_type: str,
        relationship: str,
        start_date: datetime = None,
        end_date: datetime = None,
        notes: str = None
    ) -> dict:
        """Create a relationship between two entities."""
        return {
            "from_entity_id": from_id,
            "from_entity_type": from_type,
            "to_entity_id": to_id,
            "to_entity_type": to_type,
            "relationship": relationship,
            "inverse_relationship": self.get_inverse_relationship(relationship),
            "category": self.get_relationship_category(relationship),
            "start_date": start_date,
            "end_date": end_date,
            "notes": notes,
            "is_active": True,
            "created_at": datetime.now()
        }

    def get_contact_types(self) -> List[dict]:
        """Get all contact types with labels."""
        labels = {
            ContactType.EMPLOYER: "Employer/Company",
            ContactType.EMPLOYEE: "Employee",
            ContactType.SPOUSE: "Spouse",
            ContactType.PARENT: "Parent",
            ContactType.CHILD: "Child",
            ContactType.ATTORNEY: "Attorney",
            ContactType.PETITIONER: "Petitioner",
            ContactType.BENEFICIARY: "Beneficiary",
            ContactType.REFERENCE: "Reference",
            ContactType.EXPERT_WITNESS: "Expert Witness",
            ContactType.OTHER: "Other"
        }
        return [{"value": t.value, "label": labels.get(t, t.value)} for t in ContactType]

    def get_relationship_types(self) -> List[dict]:
        """Get all relationship types."""
        return [
            {"value": "employer", "label": "Employer of"},
            {"value": "employee", "label": "Employee of"},
            {"value": "spouse", "label": "Spouse of"},
            {"value": "parent", "label": "Parent of"},
            {"value": "child", "label": "Child of"},
            {"value": "attorney", "label": "Attorney for"},
            {"value": "petitioner", "label": "Petitioner for"},
            {"value": "beneficiary", "label": "Beneficiary of"},
            {"value": "reference", "label": "Reference for"},
            {"value": "expert_witness", "label": "Expert Witness for"},
            {"value": "related", "label": "Related to"}
        ]


# SQL for contacts tables
CREATE_CONTACTS_TABLE = """
CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    contact_type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    title VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'USA',
    website VARCHAR(255),
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id),
    org_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(contact_type);
CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
CREATE INDEX IF NOT EXISTS ix_contacts_org_id ON contacts(org_id);

CREATE TABLE IF NOT EXISTS entity_relationships (
    id SERIAL PRIMARY KEY,
    from_entity_id INTEGER NOT NULL,
    from_entity_type VARCHAR(50) NOT NULL,
    to_entity_id INTEGER NOT NULL,
    to_entity_type VARCHAR(50) NOT NULL,
    relationship VARCHAR(50) NOT NULL,
    inverse_relationship VARCHAR(50),
    category VARCHAR(50),
    start_date DATE,
    end_date DATE,
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id),
    UNIQUE(from_entity_id, from_entity_type, to_entity_id, to_entity_type, relationship)
);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON entity_relationships(from_entity_id, from_entity_type);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON entity_relationships(to_entity_id, to_entity_type);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON entity_relationships(relationship);
"""


# Singleton instance
contacts_service = ContactsService()
