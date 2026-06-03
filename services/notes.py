"""
CaseHub - Case Notes Service
Manage case notes with @mentions
"""
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from models.tenant import tenant_query
from sqlalchemy import text


class CaseNotesService:
    """Service for managing case notes with @mentions."""

    def __init__(self, db: Session, org_id: int = None):
        self.db = db
        self.org_id = org_id
        self.mention_pattern = re.compile(r'@(\w+)')

    def create_note(self, case_id: int, user_id: int, content: str, is_internal: bool = True, parent_id: int = None) -> Dict[str, Any]:
        """
        Create a new note for a case.
        
        Args:
            case_id: ID of the case
            user_id: ID of the user creating the note
            content: Note content (may include @mentions)
            is_internal: If True, only visible to staff
            parent_id: ID of parent note if this is a reply
        
        Returns:
            Dict with note info
        """
        from models import Case
        
        case = tenant_query(self.db, Case, self.org_id).filter(Case.id == case_id).first()
        if not case:
            return {"success": False, "error": "Case not found"}

        # Create the note
        result = self.db.execute(text("""
            INSERT INTO case_notes (case_id, user_id, content, is_internal, parent_id, created_at, updated_at)
            VALUES (:case_id, :user_id, :content, :is_internal, :parent_id, NOW(), NOW())
            RETURNING id
        """), {
            "case_id": case_id,
            "user_id": user_id,
            "content": content,
            "is_internal": is_internal,
            "parent_id": parent_id
        })
        note_id = result.fetchone()[0]
        self.db.commit()

        # Process @mentions
        mentions = self._process_mentions(note_id, content)

        # Log to audit
        try:
            self.db.execute(text("""
                INSERT INTO audit_log (action, entity_type, entity_id, user_id, description, created_at)
                VALUES ('create', 'note', :note_id, :user_id, :description, NOW())
            """), {
                "note_id": note_id,
                "user_id": user_id,
                "description": f"Added note to case #{case_id}"
            })
            self.db.commit()
        except:
            pass

        return {
            "success": True,
            "note_id": note_id,
            "mentions": mentions
        }

    def _process_mentions(self, note_id: int, content: str) -> List[Dict]:
        """Process @mentions in content and notify users."""
        from models import User
        
        mentions = self.mention_pattern.findall(content)
        mentioned_users = []
        
        for username in set(mentions):
            # Find user by name or login
            user = tenant_query(self.db, User, self.org_id).filter(
                (User.name.ilike(f"%{username}%")) | 
                (User.login_name == username)
            ).first()
            
            if user:
                # Create mention record
                self.db.execute(text("""
                    INSERT INTO note_mentions (note_id, user_id, created_at)
                    VALUES (:note_id, :user_id, NOW())
                """), {"note_id": note_id, "user_id": user.id})
                
                mentioned_users.append({
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email
                })
        
        self.db.commit()
        return mentioned_users

    def get_notes(self, case_id: int, include_internal: bool = True) -> List[Dict]:
        """Get all notes for a case."""
        query = """
            SELECT n.*, u.name as author_name, u.email as author_email
            FROM case_notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.case_id = :case_id
        """
        if not include_internal:
            query += " AND n.is_internal = false"
        query += " ORDER BY n.created_at DESC"

        notes = self.db.execute(text(query), {"case_id": case_id}).fetchall()

        result = []
        for note in notes:
            # Get mentions for this note
            mentions = self.db.execute(text("""
                SELECT u.name FROM note_mentions nm
                JOIN users u ON nm.user_id = u.id
                WHERE nm.note_id = :note_id
            """), {"note_id": note.id}).fetchall()
            
            # Get replies count
            replies = self.db.execute(text("""
                SELECT COUNT(*) FROM case_notes WHERE parent_id = :note_id
            """), {"note_id": note.id}).scalar()

            result.append({
                "id": note.id,
                "content": note.content,
                "is_internal": note.is_internal,
                "parent_id": note.parent_id,
                "author": {
                    "id": note.user_id,
                    "name": note.author_name,
                    "email": note.author_email
                },
                "mentions": [m.name for m in mentions],
                "replies_count": replies,
                "created_at": note.created_at.isoformat() if note.created_at else None,
                "updated_at": note.updated_at.isoformat() if note.updated_at else None
            })

        return result

    def get_note(self, note_id: int) -> Optional[Dict]:
        """Get a single note."""
        note = self.db.execute(text("""
            SELECT n.*, u.name as author_name
            FROM case_notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.id = :note_id
        """), {"note_id": note_id}).fetchone()

        if not note:
            return None

        return {
            "id": note.id,
            "case_id": note.case_id,
            "content": note.content,
            "is_internal": note.is_internal,
            "parent_id": note.parent_id,
            "author": note.author_name,
            "created_at": note.created_at.isoformat() if note.created_at else None
        }

    def update_note(self, note_id: int, user_id: int, content: str) -> Dict[str, Any]:
        """Update a note."""
        note = self.get_note(note_id)
        if not note:
            return {"success": False, "error": "Note not found"}

        self.db.execute(text("""
            UPDATE case_notes SET content = :content, updated_at = NOW()
            WHERE id = :note_id
        """), {"note_id": note_id, "content": content})
        
        # Reprocess mentions
        self.db.execute(text("DELETE FROM note_mentions WHERE note_id = :note_id"), {"note_id": note_id})
        mentions = self._process_mentions(note_id, content)
        
        self.db.commit()
        return {"success": True, "mentions": mentions}

    def delete_note(self, note_id: int, user_id: int) -> Dict[str, Any]:
        """Delete a note."""
        note = self.get_note(note_id)
        if not note:
            return {"success": False, "error": "Note not found"}

        self.db.execute(text("DELETE FROM case_notes WHERE id = :note_id"), {"note_id": note_id})
        self.db.commit()
        
        return {"success": True}

    def get_mentions_for_user(self, user_id: int, unread_only: bool = False) -> List[Dict]:
        """Get all mentions for a user."""
        query = """
            SELECT nm.*, n.content, n.case_id, c.case_number, u.name as author_name
            FROM note_mentions nm
            JOIN case_notes n ON nm.note_id = n.id
            JOIN cases c ON n.case_id = c.id
            JOIN users u ON n.user_id = u.id
            WHERE nm.user_id = :user_id
        """
        if unread_only:
            query += " AND nm.read_at IS NULL"
        query += " ORDER BY nm.created_at DESC LIMIT 50"

        mentions = self.db.execute(text(query), {"user_id": user_id}).fetchall()

        return [{
            "id": m.id,
            "note_id": m.note_id,
            "case_id": m.case_id,
            "case_number": m.case_number,
            "content": m.content[:100],
            "author": m.author_name,
            "read": m.read_at is not None,
            "created_at": m.created_at.isoformat() if m.created_at else None
        } for m in mentions]

    def mark_mention_read(self, mention_id: int, user_id: int) -> bool:
        """Mark a mention as read."""
        self.db.execute(text("""
            UPDATE note_mentions SET read_at = NOW()
            WHERE id = :mention_id AND user_id = :user_id
        """), {"mention_id": mention_id, "user_id": user_id})
        self.db.commit()
        return True

    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread mentions for a user."""
        return self.db.execute(text("""
            SELECT COUNT(*) FROM note_mentions
            WHERE user_id = :user_id AND read_at IS NULL
        """), {"user_id": user_id}).scalar() or 0
