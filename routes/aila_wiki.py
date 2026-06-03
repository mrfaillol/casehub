"""
CaseHub - AILA Wiki Routes
Internal knowledge base with Notion integration and AILA semantic search.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import logging
import html
import time
import os
import asyncio

logger = logging.getLogger(__name__)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

from config import settings
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
import httpx

from models import get_db
from auth import get_current_user
from i18n import get_translations

# PREFIX = "/casehub"  # Imported from template_config.py
router = APIRouter(prefix="/aila-wiki", tags=["aila-wiki"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

# Notion Configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_WIKI_DB = os.getenv("NOTION_AILA_WIKI_DB")
NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HOME_REQUEST_TIMEOUT = max(0.5, _float_env("AILA_WIKI_NOTION_TIMEOUT_SECONDS", 4.0))
NOTION_REQUEST_TIMEOUT = max(1.0, _float_env("AILA_WIKI_NOTION_DETAIL_TIMEOUT_SECONDS", 15.0))
WIKI_HOME_BUDGET_SECONDS = max(1.0, _float_env("AILA_WIKI_HOME_BUDGET_SECONDS", 6.0))

# Cache configuration
CACHE_TTL = 300  # 5 minutes
_cache: Dict[str, tuple] = {}
_last_request_time = 0
RATE_LIMIT_DELAY = 0.4

# Categories with icons
WIKI_CATEGORIES = [
    {"name": "Visa Types", "icon": "passport", "color": "primary"},
    {"name": "Procedures", "icon": "list-check", "color": "success"},
    {"name": "RFE Response", "icon": "reply", "color": "danger"},
    {"name": "Client FAQ", "icon": "question-circle", "color": "warning"},
    {"name": "Internal Guides", "icon": "book", "color": "info"},
    {"name": "Legal Updates", "icon": "gavel", "color": "secondary"}
]


def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }


def notion_configured() -> bool:
    return bool(NOTION_TOKEN and NOTION_WIKI_DB)


def cache_get(key: str):
    """Get from cache if not expired"""
    if key in _cache:
        timestamp, data = _cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
    return None


def cache_set(key: str, data: Any):
    """Set cache with timestamp"""
    _cache[key] = (time.time(), data)


async def rate_limited_request(
    url: str,
    method: str = "GET",
    json_data: dict = None,
    timeout_seconds: Optional[float] = None,
) -> Optional[dict]:
    """Make a rate-limited request to Notion API"""
    global _last_request_time
    if not notion_configured():
        return None

    elapsed = time.time() - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)

    _last_request_time = time.time()

    try:
        request_timeout = timeout_seconds or NOTION_REQUEST_TIMEOUT
        timeout = httpx.Timeout(request_timeout, connect=min(2.0, request_timeout))
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(url, headers=get_headers())
            else:
                response = await client.post(url, headers=get_headers(), json=json_data)

            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error("[AILA Wiki] Request error: %s", e)

    return None


# =============================================================================
# NOTION HELPERS
# =============================================================================

def get_title_text(prop: dict) -> str:
    """Extract text from title property"""
    title_array = prop.get("title", [])
    if title_array:
        return title_array[0].get("text", {}).get("content", "")
    return ""


def get_rich_text(prop: dict) -> str:
    """Extract text from rich_text property"""
    text_array = prop.get("rich_text", [])
    if text_array:
        return text_array[0].get("text", {}).get("content", "")
    return ""


def get_select_value(prop: dict) -> Optional[str]:
    """Extract value from select property"""
    select = prop.get("select")
    if select:
        return select.get("name")
    return None


def get_multi_select_values(prop: dict) -> List[str]:
    """Extract values from multi_select property"""
    multi_select = prop.get("multi_select", [])
    return [item.get("name", "") for item in multi_select]


def get_number_value(prop: dict) -> Optional[int]:
    """Extract value from number property"""
    return prop.get("number")


def parse_article(page: dict) -> dict:
    """Parse Notion page into article dict"""
    props = page.get("properties", {})

    return {
        "id": page["id"],
        "title": get_title_text(props.get("Title", {})),
        "slug": get_rich_text(props.get("Slug", {})),
        "category": get_select_value(props.get("Category", {})),
        "tags": get_multi_select_values(props.get("Tags", {})),
        "status": get_select_value(props.get("Status", {})),
        "summary": get_rich_text(props.get("Summary", {})),
        "priority": get_number_value(props.get("Priority", {})) or 999,
        "last_updated": page.get("last_edited_time"),
        "created": page.get("created_time"),
        "url": page.get("url"),
        "notion_id": page["id"]
    }


async def fetch_wiki_articles(
    category: str = None,
    tag: str = None,
    status: str = "Published",
    limit: int = 50,
    request_timeout: Optional[float] = None,
) -> List[dict]:
    """Fetch articles from Notion with caching"""
    cache_key = f"articles_{category}_{tag}_{status}_{limit}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Build filter
    filters = []
    if status:
        filters.append({"property": "Status", "select": {"equals": status}})
    if category:
        filters.append({"property": "Category", "select": {"equals": category}})
    if tag:
        filters.append({"property": "Tags", "multi_select": {"contains": tag}})

    body = {
        "sorts": [
            {"property": "Priority", "direction": "ascending"},
            {"timestamp": "last_edited_time", "direction": "descending"}
        ],
        "page_size": limit
    }

    if filters:
        if len(filters) > 1:
            body["filter"] = {"and": filters}
        else:
            body["filter"] = filters[0]

    url = f"{NOTION_BASE_URL}/databases/{NOTION_WIKI_DB}/query"
    data = await rate_limited_request(url, "POST", body, timeout_seconds=request_timeout)

    if data:
        articles = [parse_article(page) for page in data.get("results", [])]
        cache_set(cache_key, articles)
        return articles

    return []


async def fetch_article_by_slug(slug: str) -> Optional[dict]:
    """Fetch a single article by slug"""
    cache_key = f"article_{slug}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    body = {
        "filter": {
            "property": "Slug",
            "rich_text": {"equals": slug}
        }
    }

    url = f"{NOTION_BASE_URL}/databases/{NOTION_WIKI_DB}/query"
    data = await rate_limited_request(url, "POST", body)

    if data and data.get("results"):
        page = data["results"][0]
        article = parse_article(page)

        # Fetch content blocks
        article["content"] = await fetch_article_content(page["id"])

        cache_set(cache_key, article)
        return article

    return None


async def fetch_article_content(page_id: str) -> str:
    """Fetch full article content (blocks) from Notion"""
    url = f"{NOTION_BASE_URL}/blocks/{page_id}/children?page_size=100"
    data = await rate_limited_request(url, "GET")

    if data:
        blocks = data.get("results", [])
        return render_blocks_to_html(blocks)

    return ""


def _safe_url(u):
    u = u or "#"
    return u if (":" not in u or u.split(":", 1)[0].lower() in ("http", "https", "mailto")) else "#"


def render_rich_text(rich_text_array: List[dict]) -> str:
    """Render rich text array to HTML"""
    html_parts = []
    for item in rich_text_array:
        text = html.escape(item.get("text", {}).get("content", ""))
        annotations = item.get("annotations", {})

        if annotations.get("bold"):
            text = f"<strong>{text}</strong>"
        if annotations.get("italic"):
            text = f"<em>{text}</em>"
        if annotations.get("code"):
            text = f"<code>{text}</code>"
        if annotations.get("underline"):
            text = f"<u>{text}</u>"
        if annotations.get("strikethrough"):
            text = f"<del>{text}</del>"

        link = item.get("text", {}).get("link")
        if link:
            text = f'<a href="{html.escape(_safe_url(link.get("url", "#")))}" target="_blank">{text}</a>'

        html_parts.append(text)

    return "".join(html_parts)


def render_blocks_to_html(blocks: List[dict]) -> str:
    """Convert Notion blocks to HTML"""
    html_parts = []
    in_list = None

    for block in blocks:
        block_type = block.get("type")
        content = block.get(block_type, {})

        # Handle list transitions
        if block_type == "bulleted_list_item":
            if in_list != "ul":
                if in_list:
                    html_parts.append(f"</{in_list}>")
                html_parts.append("<ul>")
                in_list = "ul"
        elif block_type == "numbered_list_item":
            if in_list != "ol":
                if in_list:
                    html_parts.append(f"</{in_list}>")
                html_parts.append("<ol>")
                in_list = "ol"
        else:
            if in_list:
                html_parts.append(f"</{in_list}>")
                in_list = None

        # Render block
        if block_type == "paragraph":
            text = render_rich_text(content.get("rich_text", []))
            if text:
                html_parts.append(f"<p>{text}</p>")

        elif block_type == "heading_1":
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f"<h2>{text}</h2>")

        elif block_type == "heading_2":
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f"<h3>{text}</h3>")

        elif block_type == "heading_3":
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f"<h4>{text}</h4>")

        elif block_type in ["bulleted_list_item", "numbered_list_item"]:
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f"<li>{text}</li>")

        elif block_type == "code":
            text = render_rich_text(content.get("rich_text", []))
            lang = content.get("language", "")
            html_parts.append(f'<pre><code class="language-{lang}">{text}</code></pre>')

        elif block_type == "quote":
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f"<blockquote>{text}</blockquote>")

        elif block_type == "callout":
            text = render_rich_text(content.get("rich_text", []))
            icon = content.get("icon", {}).get("emoji", "💡")
            html_parts.append(f'<div class="alert alert-info"><span class="me-2">{icon}</span>{text}</div>')

        elif block_type == "divider":
            html_parts.append("<hr>")

        elif block_type == "toggle":
            text = render_rich_text(content.get("rich_text", []))
            html_parts.append(f'<details><summary>{text}</summary></details>')

    # Close any open list
    if in_list:
        html_parts.append(f"</{in_list}>")

    return "\n".join(html_parts)


async def search_notion_wiki(query: str, limit: int = 10) -> List[dict]:
    """Search articles in Notion wiki"""
    # Notion search is limited, so we fetch all published and filter
    all_articles = await fetch_wiki_articles(status="Published", limit=100)

    query_lower = query.lower()
    results = []

    for article in all_articles:
        score = 0
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = [t.lower() for t in article.get("tags", [])]

        if query_lower in title:
            score += 10
        if query_lower in summary:
            score += 5
        for tag in tags:
            if query_lower in tag:
                score += 3

        if score > 0:
            article["relevance"] = score
            results.append(article)

    results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return results[:limit]


async def search_aila_docs(query: str, n_results: int = 5) -> List[dict]:
    """Search AILA knowledge base via existing API"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"http://localhost:{settings.PORT}/api/aila/search",
                params={"query": query, "n_results": n_results}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
    except Exception as e:
        logger.error("[AILA Wiki] AILA search error: %s", e)

    return []


async def get_popular_tags() -> List[dict]:
    """Get tag counts from all articles"""
    articles = await fetch_wiki_articles(status="Published", limit=100)
    return build_popular_tags(articles)


def build_popular_tags(articles: List[dict]) -> List[dict]:
    """Get tag counts from a preloaded article list."""

    tag_counts = {}
    for article in articles:
        for tag in article.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Sort by count and return top 10
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"name": name, "count": count} for name, count in sorted_tags[:10]]


async def get_category_counts() -> Dict[str, int]:
    """Get article counts per category"""
    articles = await fetch_wiki_articles(status="Published", limit=100)
    return build_category_counts(articles)


def build_category_counts(articles: List[dict]) -> Dict[str, int]:
    """Get category counts from a preloaded article list."""
    counts = {}
    for article in articles:
        cat = article.get("category")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1

    return counts


async def load_home_data(category: Optional[str], tag: Optional[str]) -> Tuple[List[dict], List[dict], Dict[str, int]]:
    """Load Notion-backed home data within the route budget."""
    started_at = time.monotonic()
    articles = await fetch_wiki_articles(
        category=category,
        tag=tag,
        status="Published",
        limit=50,
        request_timeout=NOTION_HOME_REQUEST_TIMEOUT,
    )
    all_articles = articles
    remaining_budget = WIKI_HOME_BUDGET_SECONDS - (time.monotonic() - started_at)
    secondary_timeout = remaining_budget - 0.1
    if secondary_timeout > 0.1:
        try:
            all_articles = await asyncio.wait_for(
                fetch_wiki_articles(
                    status="Published",
                    limit=100,
                    request_timeout=min(NOTION_HOME_REQUEST_TIMEOUT, secondary_timeout),
                ),
                timeout=secondary_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("[AILA Wiki] Sidebar data timed out; preserving visible articles")
    else:
        logger.warning("[AILA Wiki] Skipping sidebar data fetch; preserving visible articles")
    return articles, build_popular_tags(all_articles), build_category_counts(all_articles)


# =============================================================================
# HTML ROUTES
# =============================================================================

@router.get("", response_class=HTMLResponse)
async def wiki_home(
    request: Request,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """AILA Wiki homepage with categories and recent articles"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    lang = request.cookies.get("lang", "en")
    t = get_translations(lang)

    try:
        articles, popular_tags, category_counts = await asyncio.wait_for(
            load_home_data(category, tag),
            timeout=WIKI_HOME_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("[AILA Wiki] Home data timed out after %.1fs; rendering empty shell", WIKI_HOME_BUDGET_SECONDS)
        articles = []
        popular_tags = []
        category_counts = {}

    # Add counts to categories
    categories = []
    for cat in WIKI_CATEGORIES:
        cat_copy = cat.copy()
        cat_copy["count"] = category_counts.get(cat["name"], 0)
        categories.append(cat_copy)

    return templates.TemplateResponse("app/aila_wiki/home.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "articles": articles,
        "categories": categories,
        "popular_tags": popular_tags,
        "selected_category": category,
        "selected_tag": tag
    })


@router.get("/article/{slug}", response_class=HTMLResponse)
async def view_article(
    request: Request,
    slug: str,
    db: Session = Depends(get_db)
):
    """View a specific wiki article"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    lang = request.cookies.get("lang", "en")
    t = get_translations(lang)

    article = await fetch_article_by_slug(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Fetch related articles (same category or tags)
    all_articles = await fetch_wiki_articles(status="Published")
    related = []
    for a in all_articles:
        if a["slug"] != slug:
            if a.get("category") == article.get("category"):
                related.append(a)
            elif any(t in article.get("tags", []) for t in a.get("tags", [])):
                related.append(a)

    # Get AILA context if article has visa types
    aila_context = None
    if article.get("tags"):
        visa_types = [t for t in article["tags"] if t in ["H-1B", "EB-1A", "EB-2 NIW", "O-1A", "L-1A", "TN"]]
        if visa_types:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(
                        f"http://localhost:{settings.PORT}/api/aila/context/{visa_types[0]}",
                        params={"topic": "requirements"}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        aila_context = data.get("context", "")[:800]
            except Exception:
                pass

    return templates.TemplateResponse("app/aila_wiki/article.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "article": article,
        "related_articles": related[:5],
        "aila_context": aila_context
    })


@router.get("/search", response_class=HTMLResponse)
async def search_wiki(
    request: Request,
    q: str = Query("", min_length=0),
    source: str = Query("all"),
    db: Session = Depends(get_db)
):
    """Combined search across Notion wiki and AILA knowledge base"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    lang = request.cookies.get("lang", "en")
    t = get_translations(lang)

    wiki_results = []
    aila_results = []

    if q and len(q) >= 2:
        if source in ["wiki", "all"]:
            wiki_results = await search_notion_wiki(q)

        if source in ["aila", "all"]:
            aila_results = await search_aila_docs(q)

    return templates.TemplateResponse("app/aila_wiki/search.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "query": q,
        "source": source,
        "wiki_results": wiki_results,
        "aila_results": aila_results,
        "total_results": len(wiki_results) + len(aila_results)
    })


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/api/search")
async def api_search(
    request: Request,
    q: str = Query(..., min_length=2),
    source: str = Query("all"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """API endpoint for AJAX search"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    results = {
        "wiki": [],
        "aila": [],
        "query": q
    }

    if source in ["wiki", "all"]:
        results["wiki"] = await search_notion_wiki(q, limit=limit)

    if source in ["aila", "all"]:
        results["aila"] = await search_aila_docs(q, n_results=limit)

    return results


@router.post("/api/cache/clear")
async def clear_cache(request: Request, db: Session = Depends(get_db)):
    """Admin: Clear wiki cache"""
    user = get_current_user(request, db)
    if not user or getattr(user, 'user_type', '') != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    global _cache
    _cache = {}
    return {"success": True, "message": "Cache cleared"}


@router.get("/api/status")
async def wiki_status():
    """Get wiki status"""
    return {
        "status": "online",
        "database_id": NOTION_WIKI_DB,
        "cache_entries": len(_cache),
        "categories": len(WIKI_CATEGORIES)
    }
