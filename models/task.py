"""
CaseHub - Task Model
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean, JSON, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref

from .base import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(String(50))  # document_collection, form_preparation, review, filing, follow_up, reminder
    status = Column(String(50), default="pending")  # pending, in_progress, completed, blocked
    priority = Column(String(20), default="medium")  # low, medium, high, urgent

    # Subtasks and dependencies
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    depends_on = Column(JSON, default=[])  # List of task IDs this depends on
    position = Column(Integer, default=0)  # For ordering within kanban column
    column_id = Column(Integer, nullable=True, index=True)  # Dynamic kanban column placement

    # Links to client/case
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)

    # Assignment
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Privacy (Equipe CaseHub 03/06: "listas privadas bem claras"). Tarefa privada só é
    # visível ao CRIADOR e ao RESPONSÁVEL (assignee), sempre org-scoped. Default
    # 'org' preserva o comportamento atual (toda a org vê) p/ não quebrar tarefas
    # existentes. visibility: 'org' | 'private'.
    visibility = Column(String(20), default="org", server_default="org")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Arquivamento (FB2 alpha UsuarioDemo): soft-archive de cartão. Antes só existia
    # "Excluir" (hard delete). Tarefa arquivada some do board mas não é apagada;
    # espelha o is_archived de kanban_columns. Default FALSE preserva o legado.
    is_archived = Column(Boolean, default=False, server_default="0")
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # Tags (comma-separated labels) and estimated hours
    tags = Column(String, nullable=True)  # e.g. "urgente,documentos,prazo"
    estimated_hours = Column(Float, nullable=True)  # estimated hours for column stats

    # Dates
    due_date = Column(Date)
    due_time = Column(String(5), nullable=True)  # "HH:MM" — horário do prazo (reloginho Trello). Date+hora exibidos no card.
    reminder_date = Column(Date)
    completed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    client = relationship("Client", backref="tasks")
    case = relationship("Case", backref="tasks")
    # Disambiguate: two FKs to users.id (assigned_to + created_by) require explicit foreign_keys.
    assignee = relationship("User", foreign_keys=[assigned_to], backref="assigned_tasks")
    creator = relationship("User", foreign_keys=[created_by], backref="created_tasks")
    subtasks = relationship("Task", backref=backref("parent_task", remote_side=[id]))
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan", order_by="TaskComment.created_at.asc()")


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    task = relationship("Task", back_populates="comments")
    user = relationship("User")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    reminder_type = Column(String(50))  # case_deadline, document_expiry, follow_up, meeting, other
    
    # Links
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    
    # Dates
    due_date = Column(DateTime(timezone=True), nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    client = relationship("Client", backref="reminders")
    case = relationship("Case", backref="reminders")
