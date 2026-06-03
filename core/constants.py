"""
CaseHub - Application Constants
Centralized configuration for timeouts, limits, and magic numbers.
"""

# HTTP client timeouts (seconds)
HTTP_TIMEOUT_SHORT = 10      # Quick health checks, simple API calls
HTTP_TIMEOUT_DEFAULT = 30    # Standard external API calls
HTTP_TIMEOUT_LONG = 120      # File uploads, large data transfers

# Rate limiting
MAX_RATE_LIMIT_ENTRIES = 10_000
RATE_LIMIT_CLEANUP_INTERVAL = 30  # seconds

# File upload
MAX_UPLOAD_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".eml", ".msg"}

# Pagination
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

# Bulk operations
MAX_BULK_ITEMS = 500

# Cache
ORG_CACHE_TTL = 300  # 5 minutes

# Search
MAX_SEARCH_LENGTH = 255
