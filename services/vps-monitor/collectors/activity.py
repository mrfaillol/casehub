"""
User Activity Collector
Real-time tracking of user activity across all CaseHub applications
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL


class ActivityCollector:
    """Manages user activity tracking and real-time feeds"""

    def __init__(self):
        self._engine = None
        self._Session = None
        # In-memory cache for very recent events (last 30 seconds)
        self._recent_events = []
        self._last_cleanup = datetime.now()

    def _get_session(self):
        """Get database session"""
        if self._engine is None:
            self._engine = create_engine(DATABASE_URL)
            self._Session = sessionmaker(bind=self._engine)
        return self._Session()

    def record_event(self, event_data: dict) -> bool:
        """Record a new activity event from frontend tracker"""
        try:
            session = self._get_session()

            # Extract data
            session_id = event_data.get('session_id', '')
            event_type = event_data.get('event_type', 'unknown')
            source = event_data.get('source', 'unknown')
            page_url = event_data.get('page_url', '/')
            page_title = event_data.get('page_title', '')
            ip_address = event_data.get('ip_address', '')
            user_agent = event_data.get('user_agent', '')
            user_id = event_data.get('user_id')
            user_email = event_data.get('user_email', '')
            user_name = event_data.get('user_name', '')
            user_type = event_data.get('user_type', 'visitor')
            element_id = event_data.get('element_id', '')
            element_type = event_data.get('element_type', '')
            element_text = event_data.get('element_text', '')[:200] if event_data.get('element_text') else ''
            metadata = event_data.get('metadata', {})
            referrer = event_data.get('referrer', '')

            # Check if admin (Victor or admin email)
            is_admin = False
            if user_email:
                is_admin = 'victor' in user_email.lower() or 'admin@' in user_email.lower()
            if user_type == 'admin':
                is_admin = True

            # Insert activity event (skip heartbeats to reduce noise)
            if event_type != 'heartbeat':
                session.execute(text("""
                    INSERT INTO user_activity
                    (session_id, user_id, user_email, user_name, user_type, source,
                     ip_address, user_agent, event_type, page_url, page_title,
                     element_id, element_type, element_text, metadata, referrer)
                    VALUES
                    (:session_id, :user_id, :user_email, :user_name, :user_type, :source,
                     :ip_address, :user_agent, :event_type, :page_url, :page_title,
                     :element_id, :element_type, :element_text, :metadata, :referrer)
                """), {
                    'session_id': session_id,
                    'user_id': user_id,
                    'user_email': user_email,
                    'user_name': user_name,
                    'user_type': user_type,
                    'source': source,
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'event_type': event_type,
                    'page_url': page_url,
                    'page_title': page_title,
                    'element_id': element_id,
                    'element_type': element_type,
                    'element_text': element_text,
                    'metadata': json.dumps(metadata) if metadata else '{}',
                    'referrer': referrer
                })

            # Update or insert active session
            session.execute(text("""
                INSERT INTO active_sessions
                (session_id, user_id, user_email, user_name, user_type, source,
                 ip_address, user_agent, current_page, current_page_title,
                 last_activity, started_at, page_views, interactions, is_admin)
                VALUES
                (:session_id, :user_id, :user_email, :user_name, :user_type, :source,
                 :ip_address, :user_agent, :current_page, :current_page_title,
                 NOW(), NOW(), :page_views, :interactions, :is_admin)
                ON CONFLICT (session_id) DO UPDATE SET
                    current_page = :current_page,
                    current_page_title = :current_page_title,
                    last_activity = NOW(),
                    page_views = active_sessions.page_views + :page_views,
                    interactions = active_sessions.interactions + :interactions,
                    user_id = COALESCE(:user_id, active_sessions.user_id),
                    user_email = COALESCE(NULLIF(:user_email, ''), active_sessions.user_email),
                    user_name = COALESCE(NULLIF(:user_name, ''), active_sessions.user_name),
                    user_type = CASE WHEN :user_type != 'visitor' THEN :user_type ELSE active_sessions.user_type END,
                    is_admin = :is_admin OR active_sessions.is_admin
            """), {
                'session_id': session_id,
                'user_id': user_id,
                'user_email': user_email,
                'user_name': user_name,
                'user_type': user_type,
                'source': source,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'current_page': page_url,
                'current_page_title': page_title,
                'page_views': 1 if event_type == 'pageview' else 0,
                'interactions': 1 if event_type in ('click', 'form_submit', 'form_interaction') else 0,
                'is_admin': is_admin
            })

            session.commit()

            # Add to recent events cache
            if event_type != 'heartbeat':
                self._recent_events.append({
                    'timestamp': datetime.now().isoformat(),
                    'session_id': session_id,
                    'user_name': user_name or f"Visitante ({ip_address[:15]}...)" if ip_address else "Visitante",
                    'user_type': user_type,
                    'is_admin': is_admin,
                    'event_type': event_type,
                    'source': source,
                    'page_url': page_url,
                    'page_title': page_title,
                    'element_text': element_text
                })
                # Keep only last 100 events in memory
                if len(self._recent_events) > 100:
                    self._recent_events = self._recent_events[-100:]

            return True

        except Exception as e:
            print(f"[ACTIVITY] Error recording event: {e}")
            return False
        finally:
            if 'session' in locals():
                session.close()

    def get_active_users(self, source: Optional[str] = None, minutes: int = 5) -> Dict[str, Any]:
        """Get all currently active users (activity in last N minutes)"""
        try:
            session = self._get_session()

            # Clean up old sessions first
            self._cleanup_stale_sessions(session)

            # Build query
            query = """
                SELECT
                    session_id, user_id, user_email, user_name, user_type,
                    source, ip_address, current_page, current_page_title,
                    last_activity, started_at, page_views, interactions, is_admin
                FROM active_sessions
                WHERE last_activity > NOW() - INTERVAL ':minutes minutes'
            """
            params = {'minutes': minutes}

            if source:
                query += " AND source = :source"
                params['source'] = source

            query += " ORDER BY is_admin DESC, last_activity DESC"

            result = session.execute(text(query.replace(':minutes', str(minutes))), params)

            users = []
            by_source = {'wordpress': 0, 'casehub': 0, 'ilc-tools': 0, 'portal': 0}

            for row in result:
                # Calculate time on site
                started = row.started_at
                time_on_site = ""
                if started:
                    diff = datetime.now() - started
                    minutes_on = int(diff.total_seconds() / 60)
                    if minutes_on < 1:
                        time_on_site = "agora"
                    elif minutes_on < 60:
                        time_on_site = f"{minutes_on}m"
                    else:
                        time_on_site = f"{minutes_on // 60}h {minutes_on % 60}m"

                # Time since last activity
                last_seen = ""
                if row.last_activity:
                    diff = datetime.now() - row.last_activity
                    secs = int(diff.total_seconds())
                    if secs < 10:
                        last_seen = "agora"
                    elif secs < 60:
                        last_seen = f"{secs}s atrás"
                    else:
                        last_seen = f"{secs // 60}m atrás"

                user_data = {
                    'session_id': row.session_id,
                    'user_id': row.user_id,
                    'user_email': row.user_email or '',
                    'user_name': row.user_name or self._format_visitor_name(row.ip_address),
                    'user_type': row.user_type or 'visitor',
                    'source': row.source,
                    'current_page': row.current_page,
                    'current_page_title': row.current_page_title or row.current_page,
                    'time_on_site': time_on_site,
                    'last_seen': last_seen,
                    'page_views': row.page_views or 0,
                    'interactions': row.interactions or 0,
                    'is_admin': row.is_admin
                }
                users.append(user_data)

                # Count by source
                src = row.source or 'wordpress'
                if src in by_source:
                    by_source[src] += 1
                else:
                    by_source[src] = 1

            return {
                'timestamp': datetime.now().isoformat(),
                'total_active': len(users),
                'by_source': by_source,
                'users': users
            }

        except Exception as e:
            print(f"[ACTIVITY] Error getting active users: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'total_active': 0,
                'by_source': {},
                'users': [],
                'error': str(e)
            }
        finally:
            if 'session' in locals():
                session.close()

    def _format_visitor_name(self, ip_address: str) -> str:
        """Format a visitor name from IP address"""
        if not ip_address:
            return "Visitante"
        # Just show partial IP for privacy
        parts = ip_address.split('.')
        if len(parts) >= 2:
            return f"Visitante ({parts[0]}.{parts[1]}.*.*)"
        return f"Visitante ({ip_address[:10]}...)"

    def get_user_timeline(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get activity timeline for a specific session"""
        try:
            session = self._get_session()

            result = session.execute(text("""
                SELECT
                    event_type, page_url, page_title, element_id, element_type,
                    element_text, metadata, created_at
                FROM user_activity
                WHERE session_id = :session_id
                ORDER BY created_at DESC
                LIMIT :limit
            """), {'session_id': session_id, 'limit': limit})

            timeline = []
            for row in result:
                timeline.append({
                    'event_type': row.event_type,
                    'page_url': row.page_url,
                    'page_title': row.page_title,
                    'element_id': row.element_id,
                    'element_type': row.element_type,
                    'element_text': row.element_text,
                    'metadata': json.loads(row.metadata) if row.metadata else {},
                    'timestamp': row.created_at.isoformat() if row.created_at else None
                })

            return timeline

        except Exception as e:
            print(f"[ACTIVITY] Error getting timeline: {e}")
            return []
        finally:
            if 'session' in locals():
                session.close()

    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """Get recent events for the live feed"""
        # Return from memory cache for speed
        return list(reversed(self._recent_events[-limit:]))

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate activity statistics"""
        try:
            session = self._get_session()

            today = datetime.now().date()

            # Today's stats
            today_visitors = session.execute(text("""
                SELECT COUNT(DISTINCT session_id) FROM user_activity
                WHERE DATE(created_at) = :today
            """), {'today': today}).scalar() or 0

            today_pageviews = session.execute(text("""
                SELECT COUNT(*) FROM user_activity
                WHERE DATE(created_at) = :today AND event_type = 'pageview'
            """), {'today': today}).scalar() or 0

            today_clicks = session.execute(text("""
                SELECT COUNT(*) FROM user_activity
                WHERE DATE(created_at) = :today AND event_type = 'click'
            """), {'today': today}).scalar() or 0

            today_forms = session.execute(text("""
                SELECT COUNT(*) FROM user_activity
                WHERE DATE(created_at) = :today AND event_type = 'form_submit'
            """), {'today': today}).scalar() or 0

            # Top pages today
            top_pages_result = session.execute(text("""
                SELECT page_url, page_title, COUNT(*) as views
                FROM user_activity
                WHERE DATE(created_at) = :today AND event_type = 'pageview'
                GROUP BY page_url, page_title
                ORDER BY views DESC
                LIMIT 10
            """), {'today': today})

            top_pages = [
                {'url': row.page_url, 'title': row.page_title or row.page_url, 'views': row.views}
                for row in top_pages_result
            ]

            # Active now
            active_now = session.execute(text("""
                SELECT COUNT(*) FROM active_sessions
                WHERE last_activity > NOW() - INTERVAL '5 minutes'
            """)).scalar() or 0

            return {
                'active_now': active_now,
                'today': {
                    'visitors': today_visitors,
                    'pageviews': today_pageviews,
                    'clicks': today_clicks,
                    'form_submissions': today_forms
                },
                'top_pages': top_pages
            }

        except Exception as e:
            print(f"[ACTIVITY] Error getting stats: {e}")
            return {'error': str(e)}
        finally:
            if 'session' in locals():
                session.close()

    def _cleanup_stale_sessions(self, session, minutes: int = 15):
        """Remove sessions with no activity in N minutes"""
        # Only cleanup every 5 minutes
        if (datetime.now() - self._last_cleanup).total_seconds() < 300:
            return

        try:
            session.execute(text("""
                DELETE FROM active_sessions
                WHERE last_activity < NOW() - INTERVAL ':minutes minutes'
            """.replace(':minutes', str(minutes))))
            session.commit()
            self._last_cleanup = datetime.now()
        except Exception as e:
            print(f"[ACTIVITY] Error cleaning up sessions: {e}")


# Singleton instance
activity_collector = ActivityCollector()
