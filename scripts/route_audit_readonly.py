#!/usr/bin/env python3
"""Read-only visual/HTTP route audit for CaseHub.

The script logs in once per viewport, visits static GET HTML routes, records
HTTP/navigation/runtime/layout signals, and writes sanitized local reports.
It does not click app actions or send mutating requests.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception as exc:  # pragma: no cover - surfaced to CLI
    print(f"ERROR: python playwright is required: {exc}", file=sys.stderr)
    sys.exit(2)


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "wide": {"width": 1920, "height": 1080},
    "mobile": {"width": 393, "height": 852},
}

CHROMIUM_LAUNCH_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
]

RECOVERABLE_BROWSER_ERRORS = (
    "err_internet_disconnected",
    "err_network_changed",
    "err_name_not_resolved",
    "chrome-error://chromewebdata",
    "target page, context or browser has been closed",
    "browser has been closed",
)

APP_ROUTE_SUFFIX_MAP = {
    "root": "/",
    "casehub_root": "",
    "showcase_page": "showcase",
    "login_page": "login",
    "dashboard": "dashboard",
    "manual_page": "manual",
    "health_check": "/api/health",
}

SKIP_FUNCS = {
    "logout",
    "set_language",
    "whatsapp_page",
    "bot_status_proxy",
}

PRIORITY_SUFFIXES = {
    "login",
    "dashboard",
    "controladoria",
    "controladoria/indices",
    "calendar",
    "calendar/agenda",
    "clients",
    "cases",
    "tasks/kanban",
    "documents",
    "emails",
    "settings",
    "admin",
    "tools",
    "tribunal",
    "prazos",
    "whatsapp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Base origin, e.g. https://casehub.example.com")
    parser.add_argument("--product", default="lite", choices=["lite", "immigration", "whitelabel"])
    parser.add_argument("--prefix", default="", help="Application path prefix. Defaults to config.py Settings.PREFIX")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--viewports", default="desktop,mobile")
    parser.add_argument("--email", default=os.environ.get("CASEHUB_AUDIT_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("CASEHUB_AUDIT_PASSWORD", ""))
    parser.add_argument("--max-routes", type=int, default=0)
    parser.add_argument("--route-regex", default="", help="Only audit routes whose path matches this regular expression.")
    parser.add_argument("--screenshot", choices=["failures", "all", "none"], default="failures")
    parser.add_argument("--timeout-ms", type=int, default=18000)
    parser.add_argument("--restart-every", type=int, default=35, help="Restart the browser context after N routes per viewport")
    parser.add_argument(
        "--dismiss-release-notice",
        action="store_true",
        help="Dismiss the CaseHub release notice before measuring or screenshotting route evidence.",
    )
    return parser.parse_args()


def _literal_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _list_assignment(tree: ast.AST, name: str) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if isinstance(node.value, ast.List):
            return [_literal_string(item) for item in node.value.elts if _literal_string(item)]
    return []


def _class_attr_string(tree: ast.AST, class_name: str, attr_name: str) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            target = getattr(item, "target", None)
            if isinstance(target, ast.Name) and target.id == attr_name:
                return _literal_string(getattr(item, "value", ast.Constant(value="")))
    return ""


def discover_prefix(root: Path) -> str:
    try:
        tree = ast.parse((root / "config.py").read_text())
    except (FileNotFoundError, SyntaxError):
        return "/casehub"
    return _class_attr_string(tree, "Settings", "PREFIX") or "/casehub"


def discover_release_notice_id(root: Path) -> str:
    env_notice_id = os.environ.get("CASEHUB_RELEASE_NOTICE_ID", "")
    if env_notice_id:
        return env_notice_id
    fallback_id = "vieira-salles-2026-05-04-pdpj-beta"
    try:
        tree = ast.parse((root / "config.py").read_text())
    except (FileNotFoundError, SyntaxError):
        return fallback_id
    return _class_attr_string(tree, "Settings", "CASEHUB_RELEASE_NOTICE_ID") or fallback_id


def _product_modules(root: Path, product: str) -> set[str]:
    tree = ast.parse((root / "core" / "app_factory.py").read_text())
    core = _list_assignment(tree, "CORE_ROUTERS")
    immigration = _list_assignment(tree, "IMMIGRATION_ROUTERS")
    lite = _list_assignment(tree, "LITE_ROUTERS")
    whitelabel = _list_assignment(tree, "WHITELABEL_ROUTERS")
    communications = _list_assignment(tree, "COMMUNICATION_ROUTERS")
    if product == "lite":
        return set(core + lite + communications)
    if product == "whitelabel":
        return set(core + whitelabel + communications)
    return set(core + immigration + communications)


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func_name = getattr(call.func, "id", getattr(call.func, "attr", ""))
        if func_name != "APIRouter":
            continue
        prefix = ""
        for kw in call.keywords:
            if kw.arg == "prefix":
                prefix = _literal_string(kw.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _templates_used(fn: ast.AST) -> list[str]:
    templates: list[str] = []
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        if isinstance(sub.func, ast.Attribute) and sub.func.attr == "TemplateResponse":
            if sub.args:
                name = _literal_string(sub.args[0])
                if name:
                    templates.append(name)
    return sorted(set(templates))


def _normalize_path(*parts: str) -> str:
    out = "/".join(part.strip("/") for part in parts if part and part != "/")
    return "/" + out if out else "/"


def _app_route_map(prefix: str) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for name, suffix in APP_ROUTE_SUFFIX_MAP.items():
        mapped[name] = suffix if suffix.startswith("/") else _normalize_path(prefix, suffix)
    return mapped


def _priority_paths(prefix: str) -> set[str]:
    return {_normalize_path(prefix, suffix) for suffix in PRIORITY_SUFFIXES}


def _expr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _expr_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    return ""


def discover_routes(root: Path, product: str, prefix: str) -> list[dict[str, Any]]:
    modules = _product_modules(root, product)
    routes: list[dict[str, Any]] = []
    app_route_map = _app_route_map(prefix)

    for path in sorted((root / "routes").glob("*.py")):
        if path.stem not in modules:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                if dec.func.attr != "get":
                    continue
                owner = getattr(dec.func.value, "id", "")
                if owner not in prefixes:
                    continue
                route_part = _literal_string(dec.args[0]) if dec.args else ""
                if "{" in route_part or ":" in route_part:
                    continue
                templates = _templates_used(node)
                response_class = ""
                for kw in dec.keywords:
                    if kw.arg == "response_class":
                        response_class = _expr_name(kw.value)
                if not templates and "HTMLResponse" not in response_class:
                    continue
                route_path = _normalize_path(prefix, prefixes[owner], route_part)
                routes.append(
                    {
                        "path": route_path,
                        "module": str(path.relative_to(root)),
                        "line": node.lineno,
                        "function": node.name,
                        "templates": templates,
                    }
                )

    app_factory = ast.parse((root / "core" / "app_factory.py").read_text())
    for node in ast.walk(app_factory):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in SKIP_FUNCS or node.name not in app_route_map:
            continue
        routes.append(
            {
                "path": app_route_map[node.name],
                "module": "core/app_factory.py",
                "line": node.lineno,
                "function": node.name,
                "templates": _templates_used(node),
            }
        )

    dedup: dict[str, dict[str, Any]] = {}
    for item in routes:
        dedup.setdefault(item["path"], item)

    priority_paths = _priority_paths(prefix)
    return sorted(dedup.values(), key=lambda item: (item["path"] not in priority_paths, item["path"]))


def login(page: Any, base_url: str, prefix: str, email: str, password: str, timeout_ms: int) -> dict[str, Any]:
    if not email or not password:
        return {"attempted": False, "ok": False, "url": "", "reason": "missing credentials"}

    reason = ""
    try:
        login_path = _normalize_path(prefix, "login")
        try:
            page.goto(urljoin(base_url, login_path), wait_until="domcontentloaded", timeout=timeout_ms)
            if page.url.startswith("chrome-error://"):
                raise RuntimeError(f"login page failed to load: {page.url}")
        except PlaywrightTimeoutError as exc:
            reason = f"login page timeout before form fill: {str(exc)[:160]}"
        form_timeout = max(5000, min(timeout_ms, 15000))
        page.wait_for_selector('input[name="email"], input[type="email"], #email, #username', timeout=form_timeout)
        page.wait_for_selector('input[name="password"], input[type="password"], #password', timeout=form_timeout)
        page.evaluate(
            """({ email, password }) => {
              const emailInput = document.querySelector('input[name="email"], input[type="email"], #email, #username');
              const passwordInput = document.querySelector('input[name="password"], input[type="password"], #password');
              if (emailInput) {
                emailInput.value = email;
                emailInput.dispatchEvent(new Event('input', { bubbles: true }));
                emailInput.dispatchEvent(new Event('change', { bubbles: true }));
              }
              if (passwordInput) {
                passwordInput.value = password;
                passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
                passwordInput.dispatchEvent(new Event('change', { bubbles: true }));
              }
              const button = document.querySelector('button[type="submit"], input[type="submit"]');
              const form = button ? button.closest('form') : document.querySelector('form');
              if (form && form.requestSubmit) {
                form.requestSubmit(button || undefined);
              } else if (button) {
                button.click();
              } else if (form) {
                form.submit();
              }
            }""",
            {"email": email, "password": password},
        )
        try:
            page.wait_for_url(lambda url: "/login" not in url, timeout=timeout_ms)
        except PlaywrightTimeoutError as exc:
            reason = f"login redirect timed out: {str(exc)[:160]}"
        if page.url.startswith("chrome-error://"):
            reason = f"login navigation failed: {page.url}"
        elif "/login" in page.url:
            try:
                page.goto(urljoin(base_url, _normalize_path(prefix, "dashboard")), wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError as exc:
                reason = f"dashboard verification timed out after login: {str(exc)[:160]}"
        ok = "/login" not in page.url and not page.url.startswith("chrome-error://")
        return {"attempted": True, "ok": ok, "url": page.url, "reason": "" if ok else reason or "still on login"}
    except Exception as exc:
        return {"attempted": True, "ok": False, "url": getattr(page, "url", ""), "reason": str(exc)[:220]}


def _release_notice_storage_key(notice_id: str) -> str:
    return f"casehub-release-notice:{notice_id}"


def release_notice_init_script(notice_id: str) -> str:
    storage_key = json.dumps(_release_notice_storage_key(notice_id))
    return f"""(() => {{
      try {{
        window.localStorage.setItem({storage_key}, "1");
        window.localStorage.removeItem("maestro-docked");
        window.localStorage.removeItem("split-open");
      }} catch (_) {{}}
    }})();"""


def dismiss_release_notice(page: Any, notice_id: str) -> None:
    page.evaluate(
        """(storageKey) => {
          try {
            window.localStorage.setItem(storageKey, '1');
          } catch (_) {}
          const notice = document.querySelector('[data-casehub-release-notice]');
          if (notice) {
            notice.hidden = true;
            notice.setAttribute('hidden', '');
            notice.style.display = 'none';
          }
          document.documentElement.classList.remove('casehub-release-notice-open');
        }""",
        _release_notice_storage_key(notice_id),
    )


def dismiss_blocking_route_overlays(page: Any) -> None:
    page.evaluate(
        """() => {
          try {
            window.localStorage.removeItem('maestro-docked');
            window.localStorage.removeItem('split-open');
          } catch (_) {}

          const compact = window.matchMedia && window.matchMedia('(max-width: 1040px)').matches;
          const drawer = document.getElementById('maestro-drawer');
          const overlay = document.getElementById('maestro-overlay');
          const fab = document.getElementById('maestro-fab');
          const main = document.querySelector('.main-content');

          if (drawer) {
            drawer.style.right = compact ? '-105vw' : '-400px';
            drawer.setAttribute('aria-hidden', 'true');
          }
          if (overlay) {
            overlay.style.display = 'none';
            overlay.setAttribute('aria-hidden', 'true');
          }
          if (main) {
            main.style.marginRight = '';
          }
          if (fab) {
            fab.style.right = compact ? '12px' : '24px';
          }
          if ('maestroOpen' in window) {
            window.maestroOpen = false;
          }
          if ('maestroDocked' in window) {
            window.maestroDocked = false;
          }
        }"""
    )


def measure_page(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
          const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
          const offscreen = [];
          const smallTargets = [];
          const blue = [];
          const visible = (el) => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.visibility !== 'hidden' && s.display !== 'none' &&
              r.width > 0 && r.height > 0 &&
              r.bottom > 0 && r.top < viewportHeight &&
              r.right > 0 && r.left < viewportWidth;
          };
          const label = (el) => {
            const cls = String(el.className || '').replace(/\\s+/g, '.').slice(0, 80);
            const id = el.id ? '#' + el.id : '';
            return `${el.tagName.toLowerCase()}${id}${cls ? '.' + cls : ''}`;
          };
          for (const el of Array.from(document.querySelectorAll('body *'))) {
            if (!visible(el)) continue;
            const r = el.getBoundingClientRect();
            if ((r.right > viewportWidth + 3 || r.left < -3) && r.width > 24 && offscreen.length < 10) {
              offscreen.push({ element: label(el), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width) });
            }
            const roleButton = el.matches('button, a, input, select, textarea, [role="button"], [tabindex]');
            if (roleButton && (r.width < 44 || r.height < 44) && smallTargets.length < 10) {
              smallTargets.push({ element: label(el), width: Math.round(r.width), height: Math.round(r.height) });
            }
            const s = getComputedStyle(el);
            if (blue.length < 10 && [s.color, s.backgroundColor, s.borderColor].includes('rgb(13, 110, 253)')) {
              blue.push(label(el));
            }
          }
          const text = document.body ? document.body.innerText || '' : '';
          return {
            title: document.title || '',
            bodyTextLength: text.length,
            loginVisible: !!document.querySelector('input[type="password"]'),
            releaseNoticeOpen: document.documentElement.classList.contains('casehub-release-notice-open') ||
              !!document.querySelector('[data-casehub-release-notice]:not([hidden])'),
            maestroDrawerOpen: (() => {
              const drawer = document.getElementById('maestro-drawer');
              if (!drawer) return false;
              const style = getComputedStyle(drawer);
              const rect = drawer.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' &&
                rect.width > 0 && rect.height > 0 &&
                rect.left < viewportWidth - 24 && rect.right > 24;
            })(),
            horizontalOverflow: document.documentElement.scrollWidth > viewportWidth + 2,
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: viewportWidth,
            scrollHeight: document.documentElement.scrollHeight,
            clientHeight: viewportHeight,
            offscreen,
            smallTargets,
            bootstrapBlue: blue,
            internalServerErrorText: /internal server error|traceback|exception/i.test(text),
            modalCount: document.querySelectorAll('.modal.show, [role="dialog"][open]').length,
            blockingDialogOpen: Array.from(document.querySelectorAll('.modal.show, [role="dialog"][open]')).some(visible)
          };
        }"""
    )


def severity_for(result: dict[str, Any]) -> str:
    status = result.get("status") or 0
    if result.get("auditTransportError"):
        return "audit-error"
    if result.get("navigationError") or status >= 500 or result["metrics"].get("internalServerErrorText"):
        return "critical"
    if result.get("evidenceInvalid"):
        return "high"
    if status >= 400 or result.get("pageErrors"):
        return "high"
    if (
        result.get("consoleErrors")
        or result["metrics"].get("horizontalOverflow")
        or result.get("redirectedToLogin")
        or result.get("loadIdleTimeout")
    ):
        return "medium"
    if result["metrics"].get("offscreen") or result["metrics"].get("smallTargets") or result["metrics"].get("bootstrapBlue"):
        return "low"
    return "ok"


def audit_route(
    context: Any,
    base_url: str,
    prefix: str,
    route: dict[str, Any],
    viewport: str,
    timeout_ms: int,
    screenshot_mode: str,
    screenshot_dir: Path,
    dismiss_notice: bool,
    release_notice_id: str,
) -> dict[str, Any]:
    console_errors: list[str] = []
    page_errors: list[str] = []
    page = None
    try:
        page = context.new_page()
    except Exception as exc:
        error = str(exc)[:220]
        return {
            "route": route,
            "viewport": viewport,
            "status": None,
            "finalUrl": "",
            "redirectedToLogin": False,
            "navigationError": error,
            "consoleErrors": [],
            "pageErrors": [],
            "loadIdleTimeout": False,
            "metrics": {
                "title": "",
                "bodyTextLength": 0,
                "loginVisible": False,
                "releaseNoticeOpen": False,
                "maestroDrawerOpen": False,
                "blockingDialogOpen": False,
                "horizontalOverflow": False,
                "offscreen": [],
                "smallTargets": [],
                "bootstrapBlue": [],
                "internalServerErrorText": False,
            },
            "severity": "audit-error" if is_audit_transport_error(error, "") else "critical",
            "auditTransportError": is_audit_transport_error(error, ""),
            "evidenceType": "audit-transport" if is_audit_transport_error(error, "") else ("route-no-popup" if dismiss_notice else "route"),
            "evidenceInvalid": False,
        }
    page.on("console", lambda msg: console_errors.append(msg.text[:300]) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)[:300]))

    status = None
    error = ""
    load_idle_timeout = False
    try:
        response = page.goto(urljoin(base_url, route["path"]), wait_until="domcontentloaded", timeout=timeout_ms)
        status = response.status if response else None
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            load_idle_timeout = True
    except PlaywrightTimeoutError as exc:
        error = f"timeout: {str(exc)[:180]}"
    except Exception as exc:
        error = str(exc)[:220]

    if dismiss_notice:
        try:
            dismiss_release_notice(page, release_notice_id)
        except Exception as exc:
            page_errors.append(f"release notice dismissal failed: {str(exc)[:220]}")
        try:
            dismiss_blocking_route_overlays(page)
        except Exception as exc:
            page_errors.append(f"route overlay dismissal failed: {str(exc)[:220]}")

    try:
        metrics = measure_page(page)
    except Exception as exc:
        metrics = {
            "title": "",
            "bodyTextLength": 0,
            "loginVisible": False,
            "releaseNoticeOpen": False,
            "maestroDrawerOpen": False,
            "blockingDialogOpen": False,
            "horizontalOverflow": False,
            "offscreen": [],
            "smallTargets": [],
            "bootstrapBlue": [],
            "internalServerErrorText": False,
            "measurementError": str(exc)[:220],
        }

    final_url = page.url
    login_path = _normalize_path(prefix, "login")
    redirected_to_login = route["path"] != login_path and login_path in final_url
    evidence_invalid = bool(
        dismiss_notice
        and (
            metrics.get("releaseNoticeOpen")
            or metrics.get("maestroDrawerOpen")
            or metrics.get("blockingDialogOpen")
        )
    )
    audit_transport_error = is_audit_transport_error(error, final_url)
    result = {
        "route": route,
        "viewport": viewport,
        "status": status,
        "finalUrl": final_url,
        "redirectedToLogin": redirected_to_login,
        "navigationError": error,
        "consoleErrors": [err for err in console_errors if "favicon" not in err.lower()][:5],
        "pageErrors": page_errors[:5],
        "loadIdleTimeout": load_idle_timeout,
        "metrics": metrics,
        "auditTransportError": audit_transport_error,
        "evidenceType": "audit-transport" if audit_transport_error else ("route-no-popup" if dismiss_notice else "route"),
        "evidenceInvalid": evidence_invalid,
    }
    result["severity"] = severity_for(result)
    take_shot = screenshot_mode == "all" or (
        screenshot_mode == "failures" and result["severity"] in {"critical", "high", "medium", "audit-error"}
    )
    if take_shot:
        try:
            name = re.sub(r"[^a-zA-Z0-9]+", "-", route["path"]).strip("-") or "root"
            page.screenshot(path=str(screenshot_dir / f"{viewport}-{name}.png"), full_page=False)
        except Exception:
            pass
    try:
        page.close()
    except Exception:
        pass
    return result


def needs_context_restart(result: dict[str, Any]) -> bool:
    text = " ".join(
        [
            result.get("navigationError", ""),
            result.get("finalUrl", ""),
            " ".join(result.get("pageErrors", [])),
        ]
    ).lower()
    return any(error in text for error in RECOVERABLE_BROWSER_ERRORS)


def is_audit_transport_error(navigation_error: str, final_url: str) -> bool:
    text = f"{navigation_error} {final_url}".lower()
    return any(error in text for error in RECOVERABLE_BROWSER_ERRORS)


def should_retry_after_reauth(result: dict[str, Any], prefix: str, login_result: dict[str, Any]) -> bool:
    login_path = _normalize_path(prefix, "login")
    return bool(
        login_result.get("ok")
        and result.get("redirectedToLogin")
        and result.get("route", {}).get("path") != login_path
    )


def should_reset_after_route(result: dict[str, Any], prefix: str, login_result: dict[str, Any]) -> bool:
    login_path = _normalize_path(prefix, "login")
    return bool(login_result.get("ok") and login_path in (result.get("finalUrl") or ""))


def create_blank_context(browser: Any, viewport_name: str, args: argparse.Namespace) -> Any:
    context = browser.new_context(
        viewport=VIEWPORTS[viewport_name],
        ignore_https_errors=True,
        color_scheme="light",
    )
    if args.dismiss_release_notice:
        context.add_init_script(release_notice_init_script(args.release_notice_id))
    return context


def create_context(browser: Any, viewport_name: str, args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    context = create_blank_context(browser, viewport_name, args)
    login_page = context.new_page()
    try:
        login_result = login(login_page, args.base_url, args.prefix, args.email, args.password, args.timeout_ms)
    finally:
        try:
            login_page.close()
        except Exception:
            pass
    return context, login_result


def launch_browser(pw: Any) -> Any:
    return pw.chromium.launch(headless=True, args=CHROMIUM_LAUNCH_ARGS)


def relaunch_browser(pw: Any, browser: Any) -> Any:
    try:
        browser.close()
    except Exception:
        pass
    return launch_browser(pw)


def is_retriable_login_failure(login_result: dict[str, Any]) -> bool:
    if not login_result.get("attempted") or login_result.get("ok"):
        return False
    text = f"{login_result.get('reason', '')} {login_result.get('url', '')}".lower()
    if "/login" in text and "chrome-error://" not in text and "net::" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "timeout",
            "chrome-error://",
            "net::",
            "target closed",
            "browser has been closed",
            "context closed",
            "navigation",
        )
    )


def create_context_resilient(pw: Any, browser: Any, viewport_name: str, args: argparse.Namespace) -> tuple[Any, Any, dict[str, Any]]:
    last_login_result: dict[str, Any] = {"attempted": False, "ok": False, "url": "", "reason": "not attempted"}
    max_attempts = 2
    for attempt in range(max_attempts):
        context = None
        try:
            context, login_result = create_context(browser, viewport_name, args)
            last_login_result = login_result
            if not args.email or not args.password or login_result.get("ok"):
                return browser, context, login_result
            if not is_retriable_login_failure(login_result):
                return browser, context, login_result
            if attempt == max_attempts - 1:
                login_result.setdefault("reason", last_login_result.get("reason", "login failed after retries"))
                return browser, context, login_result
        except Exception as exc:
            last_login_result = {"attempted": True, "ok": False, "url": "", "reason": str(exc)[:220]}
            if attempt == max_attempts - 1:
                if context:
                    return browser, context, last_login_result
                try:
                    context = create_blank_context(browser, viewport_name, args)
                except Exception:
                    browser = relaunch_browser(pw, browser)
                    context = create_blank_context(browser, viewport_name, args)
                return browser, context, last_login_result

        try:
            if context:
                context.close()
        except Exception:
            pass
        if attempt < max_attempts - 1:
            browser = relaunch_browser(pw, browser)

    context = create_blank_context(browser, viewport_name, args)
    return browser, context, last_login_result


def write_report(out_dir: Path, payload: dict[str, Any]) -> None:
    results = payload["results"]
    routes = payload["routes"]
    counts: dict[str, int] = {}
    for result in results:
        counts[result["severity"]] = counts.get(result["severity"], 0) + 1

    lines = [
        f"# CaseHub Route Audit — {payload['label']}",
        "",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Product: `{payload['product']}`",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Static GET HTML routes discovered: `{len(routes)}`",
        f"- Viewports: `{', '.join(payload['viewports'])}`",
        f"- Login attempted: `{payload['login'].get('attempted')}`; ok: `{payload['login'].get('ok')}`",
        f"- Release notice / blocking overlay dismissal: `{payload.get('auditOptions', {}).get('dismissReleaseNotice')}`",
        f"- Result counts: `{json.dumps(counts, sort_keys=True)}`",
        "",
        "## Findings",
        "",
        "| Severity | Viewport | Path | Status | Signal |",
        "|---|---:|---|---:|---|",
    ]

    severity_order = ["critical", "high", "medium", "low", "audit-error", "ok"]
    interesting = [item for item in results if item["severity"] != "ok"]
    for item in sorted(
        interesting,
        key=lambda x: (
            severity_order.index(x["severity"]) if x["severity"] in severity_order else len(severity_order),
            x["route"]["path"],
            x["viewport"],
        ),
    ):
        metrics = item["metrics"]
        signals: list[str] = []
        if item.get("navigationError"):
            signals.append(item["navigationError"])
        if item.get("auditTransportError"):
            signals.append("audit transport error; rerun required before product classification")
        if item.get("redirectedToLogin"):
            signals.append("redirected to login")
        if item.get("consoleErrors"):
            signals.append(f"{len(item['consoleErrors'])} console error(s)")
        if item.get("pageErrors"):
            signals.append(f"{len(item['pageErrors'])} page error(s)")
        if item.get("loadIdleTimeout"):
            signals.append("networkidle not reached within 5s")
        if item.get("evidenceInvalid"):
            invalid_signals = []
            if metrics.get("releaseNoticeOpen"):
                invalid_signals.append("release popup visible")
            if metrics.get("maestroDrawerOpen"):
                invalid_signals.append("Maestro drawer visible")
            if metrics.get("blockingDialogOpen"):
                invalid_signals.append("blocking dialog visible")
            signals.append(f"invalid route evidence: {', '.join(invalid_signals) or 'blocking overlay visible'}")
        if metrics.get("horizontalOverflow"):
            signals.append(f"horizontal overflow {metrics.get('scrollWidth')} > {metrics.get('clientWidth')}")
        if metrics.get("offscreen"):
            signals.append(f"{len(metrics['offscreen'])} offscreen element(s)")
        if metrics.get("smallTargets"):
            signals.append(f"{len(metrics['smallTargets'])} small tap target(s)")
        if metrics.get("bootstrapBlue"):
            signals.append(f"{len(metrics['bootstrapBlue'])} bootstrap-blue element(s)")
        if metrics.get("internalServerErrorText"):
            signals.append("body contains server-error text")
        lines.append(
            f"| `{item['severity']}` | `{item['viewport']}` | `{item['route']['path']}` | `{item.get('status') or ''}` | "
            f"{'; '.join(signals)[:400]} |"
        )

    if not interesting:
        lines.append("| `ok` | `all` | `all` |  | no findings recorded |")

    lines += [
        "",
        "## Route Matrix",
        "",
        "| Path | Source | Template |",
        "|---|---|---|",
    ]
    for route in routes:
        templates = ", ".join(route.get("templates") or [])
        lines.append(f"| `{route['path']}` | `{route['module']}:{route['line']}` | `{templates}` |")

    (out_dir / "report.md").write_text("\n".join(lines) + "\n")
    (out_dir / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    root = Path.cwd()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args.prefix = args.prefix or discover_prefix(root)
    args.release_notice_id = discover_release_notice_id(root)

    routes = discover_routes(root, args.product, args.prefix)
    if args.route_regex:
        try:
            route_pattern = re.compile(args.route_regex)
        except re.error as exc:
            raise SystemExit(f"Invalid --route-regex: {exc}") from exc
        routes = [route for route in routes if route_pattern.search(route["path"])]
    if args.max_routes:
        routes = routes[: args.max_routes]

    viewports = [vp.strip() for vp in args.viewports.split(",") if vp.strip()]
    invalid = [vp for vp in viewports if vp not in VIEWPORTS]
    if invalid:
        raise SystemExit(f"Unknown viewport(s): {', '.join(invalid)}")

    label = re.sub(r"[^a-z0-9]+", "-", args.base_url.lower()).strip("-")
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    all_results: list[dict[str, Any]] = []
    login_result: dict[str, Any] = {"attempted": False, "ok": False}
    screenshot_dir = out_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            for viewport_name in viewports:
                browser, context, this_login = create_context_resilient(pw, browser, viewport_name, args)
                current_login = this_login
                if viewport_name == viewports[0]:
                    login_result = this_login

                for idx, route in enumerate(routes, start=1):
                    if args.restart_every > 0 and idx > 1 and (idx - 1) % args.restart_every == 0:
                        try:
                            context.close()
                        except Exception:
                            pass
                        browser, context, current_login = create_context_resilient(pw, browser, viewport_name, args)

                    print(f"[{viewport_name}] {idx:03d}/{len(routes):03d} {route['path']}", flush=True)
                    result = audit_route(
                        context,
                        args.base_url,
                        args.prefix,
                        route,
                        viewport_name,
                        args.timeout_ms,
                        args.screenshot,
                        screenshot_dir,
                        args.dismiss_release_notice,
                        args.release_notice_id,
                    )
                    if needs_context_restart(result) or should_retry_after_reauth(result, args.prefix, current_login):
                        try:
                            context.close()
                        except Exception:
                            pass
                        browser, context, current_login = create_context_resilient(pw, browser, viewport_name, args)
                        result = audit_route(
                            context,
                            args.base_url,
                            args.prefix,
                            route,
                            viewport_name,
                            args.timeout_ms,
                            args.screenshot,
                            screenshot_dir,
                            args.dismiss_release_notice,
                            args.release_notice_id,
                        )
                    all_results.append(result)
                    if should_reset_after_route(result, args.prefix, current_login):
                        try:
                            context.close()
                        except Exception:
                            pass
                        browser, context, current_login = create_context_resilient(pw, browser, viewport_name, args)
                try:
                    context.close()
                except Exception:
                    pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

    payload = {
        "label": label,
        "baseUrl": args.base_url.rstrip("/"),
        "product": args.product,
        "generatedAt": generated_at,
        "viewports": viewports,
        "auditOptions": {
            "dismissReleaseNotice": args.dismiss_release_notice,
            "releaseNoticeId": args.release_notice_id if args.dismiss_release_notice else "",
        },
        "login": login_result,
        "routes": routes,
        "results": all_results,
    }
    write_report(out_dir, payload)
    print(f"Report: {out_dir / 'report.md'}")
    print(f"JSON: {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
