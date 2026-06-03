"""
CaseHub Lite - Lightweight CRM-only product (no immigration-specific features).
"""
from core.app_factory import create_app

app = create_app("lite")
