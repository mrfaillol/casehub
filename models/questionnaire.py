"""
CaseHub - Questionnaire Models
System for creating and managing client questionnaires/forms
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class QuestionnaireTemplate(Base):
    """Template for a questionnaire/form"""
    __tablename__ = "questionnaire_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(100))  # e.g., 'intake', 'visa_application', 'employment', 'family'

    # Target entity - what this questionnaire is for
    target_type = Column(String(50))  # 'client', 'case', 'general'
    visa_types = Column(JSON)  # List of visa types this applies to, or null for all

    # Settings
    is_active = Column(Boolean, default=True)
    is_required = Column(Boolean, default=False)
    allow_multiple = Column(Boolean, default=False)  # Can be filled multiple times

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fields = relationship("QuestionnaireField", back_populates="template", order_by="QuestionnaireField.order")
    responses = relationship("QuestionnaireResponse", back_populates="template")


class QuestionnaireField(Base):
    """Individual field/question in a questionnaire"""
    __tablename__ = "questionnaire_fields"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("questionnaire_templates.id"), nullable=False)

    # Field definition
    field_name = Column(String(100), nullable=False)  # Internal name (snake_case)
    label = Column(String(255), nullable=False)  # Display label
    label_pt = Column(String(255))  # Portuguese label
    description = Column(Text)  # Help text
    description_pt = Column(Text)  # Portuguese help text

    # Field type
    field_type = Column(String(50), nullable=False)  # text, textarea, number, date, select, multiselect, checkbox, file, section

    # Validation
    is_required = Column(Boolean, default=False)
    min_length = Column(Integer)
    max_length = Column(Integer)
    min_value = Column(Integer)
    max_value = Column(Integer)
    pattern = Column(String(255))  # Regex pattern

    # Options for select/multiselect
    options = Column(JSON)  # [{"value": "opt1", "label": "Option 1", "label_pt": "Opção 1"}, ...]

    # Conditional display
    depends_on = Column(String(100))  # Field name this depends on
    depends_value = Column(String(255))  # Value that triggers display

    # Layout
    order = Column(Integer, default=0)
    section = Column(String(100))  # Group fields into sections
    width = Column(String(20), default="full")  # full, half, third

    # Relationships
    template = relationship("QuestionnaireTemplate", back_populates="fields")


class QuestionnaireResponse(Base):
    """A completed questionnaire response"""
    __tablename__ = "questionnaire_responses"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("questionnaire_templates.id"), nullable=False)

    # Link to client/case
    client_id = Column(Integer, ForeignKey("clients.id"))
    case_id = Column(Integer, ForeignKey("cases.id"))

    # Status
    status = Column(String(50), default="draft")  # draft, submitted, reviewed, approved

    # Metadata
    submitted_by = Column(Integer, ForeignKey("users.id"))  # null if submitted by client via portal
    submitted_by_client = Column(Boolean, default=False)
    submitted_at = Column(DateTime)

    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Store all responses as JSON for easy access
    responses_data = Column(JSON)  # {"field_name": "value", ...}

    # Relationships
    template = relationship("QuestionnaireTemplate", back_populates="responses")
    field_responses = relationship("QuestionnaireFieldResponse", back_populates="response")


class QuestionnaireFieldResponse(Base):
    """Individual field response within a questionnaire response"""
    __tablename__ = "questionnaire_field_responses"

    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(Integer, ForeignKey("questionnaire_responses.id"), nullable=False)
    field_id = Column(Integer, ForeignKey("questionnaire_fields.id"), nullable=False)

    # Response value (stored as text, can be parsed based on field type)
    value = Column(Text)

    # For file uploads
    file_path = Column(String(500))

    # Relationships
    response = relationship("QuestionnaireResponse", back_populates="field_responses")
