"""
CaseHub - Application Entry Point (shim)
Delegates to core.app_factory based on CASEHUB_PRODUCT env var.

Usage:
    uvicorn app:app --host 0.0.0.0 --port 8001 --reload
    CASEHUB_PRODUCT=immigration uvicorn app:app --host 0.0.0.0 --port 8001 --reload
"""
import os
from core.app_factory import create_app

product = os.getenv("CASEHUB_PRODUCT", "lite")
app = create_app(product)
