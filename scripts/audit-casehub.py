#!/usr/bin/env python3
"""
CaseHub Lite — Full Visual & Functional Audit with Playwright
Navigates all routes, clicks interactives, screenshots light/dark + 3 viewports,
detects errors, generates structured report.
"""
import os, re, json, time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://casehub.vingren.me"
LOGIN_EMAIL = "victor@vingren.me"
LOGIN_PASS = "demo123"

VIEWPORTS = [
    {"name": "desktop", "width": 1920, "height": 1080},
    {"name": "tablet",  "width": 1024, "height": 768},
    {"name": "mobile",  "width": 375,  "height": 812},
]

ROUTES = [
    "/casehub/dashboard",
    "/casehub/tasks/kanban",
    "/casehub/calendar",
    "/casehub/documents",
    "/casehub/clients",
    "/casehub/clients/1",
    "/casehub/cases",
    "/casehub/cases/1",
    "/casehub/cases/2",
    "/casehub/cases/3",
    "/casehub/prazos",
    "/casehub/checklists",
    "/casehub/emails",
    "/casehub/billing",
    "/casehub/leads",
    "/casehub/whatsapp",
    "/casehub/controladoria",
    "/casehub/tribunal",
    "/casehub/tools",
    "/casehub/tools/rescisao",
    "/casehub/tools/horas-extras",
    "/casehub/tools/ferias",
    "/casehub/tools/correcao-monetaria",
    "/casehub/tools/pensao",
    "/casehub/tools/juros-mora",
    "/casehub/tools/honorarios",
    "/casehub/tools/custas",
    "/casehub/tools/dosimetria",
    "/casehub/tools/progressao",
    "/casehub/tools/prescricao",
    "/casehub/tools/irpf",
    "/casehub/tools/itcmd",
    "/casehub/tools/pecas",
    "/casehub/assistente",
    "/casehub/reports",
    "/casehub/settings",
    "/casehub/admin",
    "/casehub/notifications",
    "/casehub/customizacao",
    "/casehub/profile",
    "/casehub/manual",
    "/casehub/assistente/config",
]

# Portuguese accent check patterns
ACCENT_ERRORS = [
    (r'\bCalculo\b', 'Cálculo'), (r'\bRescisao\b', 'Rescisão'),
    (r'\bFerias\b', 'Férias'), (r'\bHonorarios\b', 'Honorários'),
    (r'\bCorrecao\b', 'Correção'), (r'\bPensao\b', 'Pensão'),
    (r'\bJuridico\b', 'Jurídico'), (r'\bNumero\b', 'Número'),
    (r'\bProcesso\b(?!s)', 'OK'), (r'\bPrevidenciario\b', 'Previdenciário'),
    (r'\bTributario\b', 'Tributário'), (r'\bBancario\b', 'Bancário'),
    (r'\bRelatorio\b', 'Relatório'), (r'\bInicio\b', 'Início'),
    (r'\bUltimo\b', 'Último'), (r'\bProximo\b', 'Próximo'),
    (r'\bAcoes\b', 'Ações'), (r'\bInformacoes\b', 'Informações'),
    (r'\bSituacao\b', 'Situação'), (r'\bDescricao\b', 'Descrição'),
]

# Bootstrap blue that should be CaseHub teal
WRONG_COLORS = ['#0d6efd', '#1a73e8', '#007bff', 'rgb(13, 110, 253)']

def setup_dirs():
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = Path(f"audit-screenshots/{ts}")
    base.mkdir(parents=True, exist_ok=True)
    return base, ts

def login(page):
    page.goto(f"{BASE_URL}/casehub/login", wait_until="networkidle", timeout=15000)
    page.fill('input[name="email"], input[type="email"]', LOGIN_EMAIL)
    page.fill('input[name="password"], input[type="password"]', LOGIN_PASS)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(1)
    return page.url

def safe_name(route):
    return route.replace("/casehub/", "").replace("/", "_") or "root"

def check_accent_errors(text):
    issues = []
    for pattern, correct in ACCENT_ERRORS:
        if correct == 'OK':
            continue
        matches = re.findall(pattern, text)
        if matches:
            issues.append({"found": matches[0], "should_be": correct})
    return issues

def check_wrong_colors(page):
    """Check computed styles for Bootstrap blue instead of CaseHub teal"""
    results = page.evaluate("""() => {
        const issues = [];
        const els = document.querySelectorAll('*');
        const badColors = ['rgb(13, 110, 253)', 'rgb(26, 115, 232)', 'rgb(0, 123, 255)'];
        for (let i = 0; i < Math.min(els.length, 500); i++) {
            const s = getComputedStyle(els[i]);
            for (const prop of ['color', 'backgroundColor', 'borderColor']) {
                if (badColors.includes(s[prop])) {
                    const tag = els[i].tagName.toLowerCase();
                    const cls = els[i].className?.toString().slice(0, 60) || '';
                    issues.push({element: `${tag}.${cls}`, property: prop, value: s[prop]});
                    if (issues.length > 10) return issues;
                }
            }
        }
        return issues;
    }""")
    return results

def check_overflow(page):
    """Check for horizontally overflowing elements"""
    return page.evaluate("""() => {
        const issues = [];
        const vw = window.innerWidth;
        document.querySelectorAll('*').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.right > vw + 5 && r.width > 50) {
                const tag = el.tagName.toLowerCase();
                const cls = (el.className?.toString() || '').slice(0, 40);
                issues.push({element: `${tag}.${cls}`, overflow: Math.round(r.right - vw)});
            }
        });
        return issues.slice(0, 5);
    }""")

def toggle_dark_mode(page):
    """Try to toggle dark mode via JS or button click"""
    page.evaluate("""() => {
        const html = document.documentElement;
        if (html.getAttribute('data-theme') === 'dark') {
            html.setAttribute('data-theme', 'light');
        } else {
            html.setAttribute('data-theme', 'dark');
        }
    }""")
    time.sleep(0.3)

def check_dark_mode_issues(page):
    """Check for white backgrounds or unreadable text in dark mode"""
    return page.evaluate("""() => {
        const issues = [];
        const cards = document.querySelectorAll('.card, .glass-card, .main-content, table, .modal');
        cards.forEach(el => {
            const s = getComputedStyle(el);
            const bg = s.backgroundColor;
            // Check for pure white or very light backgrounds in dark mode
            if (bg === 'rgb(255, 255, 255)' || bg === 'rgba(255, 255, 255, 1)') {
                const tag = el.tagName.toLowerCase();
                const cls = (el.className?.toString() || '').slice(0, 50);
                issues.push({element: `${tag}.${cls}`, issue: 'white background in dark mode', bg: bg});
            }
        });
        return issues.slice(0, 10);
    }""")

def find_clickables(page):
    """Find all clickable elements on the page"""
    return page.evaluate("""() => {
        const items = [];
        // Buttons
        document.querySelectorAll('button:not([disabled])').forEach((el, i) => {
            if (i < 15) {
                const text = (el.textContent || '').trim().slice(0, 30);
                const cls = (el.className || '').slice(0, 40);
                items.push({type: 'button', text, selector: `button:nth-of-type(${i+1})`, cls});
            }
        });
        // Tabs / nav-links
        document.querySelectorAll('.nav-link, [data-bs-toggle="tab"], [role="tab"]').forEach((el, i) => {
            const text = (el.textContent || '').trim().slice(0, 30);
            items.push({type: 'tab', text, selector: `.nav-link:nth-of-type(${i+1})`});
        });
        // Dropdowns
        document.querySelectorAll('select').forEach((el, i) => {
            const name = el.name || el.id || `select-${i}`;
            items.push({type: 'select', text: name});
        });
        return items;
    }""")

def audit_route(page, route, screenshot_dir, issues_list):
    name = safe_name(route)
    url = f"{BASE_URL}{route}"

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    try:
        resp = page.goto(url, wait_until="networkidle", timeout=15000)
        status = resp.status if resp else 0
    except Exception as e:
        issues_list.append({
            "route": route, "severity": "critical",
            "category": "navigation", "issue": f"Failed to load: {str(e)[:100]}"
        })
        return

    if status >= 400:
        issues_list.append({
            "route": route, "severity": "critical",
            "category": "http_error", "issue": f"HTTP {status}"
        })

    time.sleep(0.5)

    # Check page text for accent errors
    try:
        text = page.inner_text("body")
        accent_issues = check_accent_errors(text)
        for ai in accent_issues:
            issues_list.append({
                "route": route, "severity": "low",
                "category": "portuguese", "issue": f"'{ai['found']}' → '{ai['should_be']}'"
            })
    except:
        pass

    # Check wrong colors
    try:
        color_issues = check_wrong_colors(page)
        for ci in color_issues:
            issues_list.append({
                "route": route, "severity": "medium",
                "category": "design", "issue": f"Bootstrap blue on {ci['element']}: {ci['property']}"
            })
    except:
        pass

    # Console errors
    for ce in console_errors[:3]:
        if 'favicon' not in ce.lower():
            issues_list.append({
                "route": route, "severity": "medium",
                "category": "js_error", "issue": ce[:120]
            })

    # Light mode screenshot
    page.screenshot(path=str(screenshot_dir / f"{name}_light.png"), full_page=False)

    # Check overflow
    try:
        overflows = check_overflow(page)
        for ov in overflows:
            issues_list.append({
                "route": route, "severity": "medium",
                "category": "responsiveness", "issue": f"Overflow: {ov['element']} by {ov['overflow']}px"
            })
    except:
        pass

    # Dark mode
    toggle_dark_mode(page)
    page.screenshot(path=str(screenshot_dir / f"{name}_dark.png"), full_page=False)

    try:
        dark_issues = check_dark_mode_issues(page)
        for di in dark_issues:
            issues_list.append({
                "route": route, "severity": "high",
                "category": "dark_mode", "issue": f"{di['issue']}: {di['element']}"
            })
    except:
        pass

    # Back to light
    toggle_dark_mode(page)

    # Find and screenshot clickable interactions
    try:
        clickables = find_clickables(page)
        clicked = 0
        for item in clickables[:8]:
            if clicked >= 4:
                break
            try:
                if item['type'] == 'tab':
                    tabs = page.query_selector_all('.nav-link, [data-bs-toggle="tab"]')
                    for tab in tabs:
                        tab_text = (tab.inner_text() or "").strip()
                        if tab_text and tab_text == item['text']:
                            tab.click()
                            time.sleep(0.3)
                            page.screenshot(
                                path=str(screenshot_dir / f"{name}_click_{clicked}.png"),
                                full_page=False
                            )
                            clicked += 1
                            break
            except:
                pass
    except:
        pass

def generate_report(issues, screenshot_dir, ts):
    critical = [i for i in issues if i['severity'] == 'critical']
    high = [i for i in issues if i['severity'] == 'high']
    medium = [i for i in issues if i['severity'] == 'medium']
    low = [i for i in issues if i['severity'] == 'low']

    report = f"""# CaseHub Lite Audit Report — {ts}

## Summary
- **Routes tested**: {len(ROUTES)}
- **Total issues found**: {len(issues)}
- **Critical**: {len(critical)} | **High**: {len(high)} | **Medium**: {len(medium)} | **Low**: {len(low)}
- **Screenshots**: {screenshot_dir}/

---

## Critical Issues (500 errors, broken pages)
"""
    if critical:
        report += "| Route | Issue |\n|-------|-------|\n"
        for i in critical:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    report += "\n## Dark Mode Issues\n"
    dark = [i for i in issues if i['category'] == 'dark_mode']
    if dark:
        report += "| Route | Issue |\n|-------|-------|\n"
        for i in dark:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    report += "\n## Design Inconsistencies (wrong colors, missing glass)\n"
    design = [i for i in issues if i['category'] == 'design']
    if design:
        report += "| Route | Issue |\n|-------|-------|\n"
        for i in design:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    report += "\n## Responsiveness Issues\n"
    resp = [i for i in issues if i['category'] == 'responsiveness']
    if resp:
        report += "| Route | Issue |\n|-------|-------|\n"
        for i in resp:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    report += "\n## JavaScript Errors\n"
    js = [i for i in issues if i['category'] == 'js_error']
    if js:
        report += "| Route | Error |\n|-------|-------|\n"
        for i in js:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    report += "\n## Portuguese Accent Errors\n"
    pt = [i for i in issues if i['category'] == 'portuguese']
    if pt:
        report += "| Route | Issue |\n|-------|-------|\n"
        for i in pt:
            report += f"| `{i['route']}` | {i['issue']} |\n"
    else:
        report += "None found.\n"

    return report

def main():
    screenshot_dir, ts = setup_dirs()
    all_issues = []

    print(f"🔍 CaseHub Audit — {ts}")
    print(f"📁 Screenshots → {screenshot_dir}/")
    print(f"🌐 {len(ROUTES)} routes × {len(VIEWPORTS)} viewports")
    print("=" * 60)

    with sync_playwright() as p:
        for vp in VIEWPORTS:
            vp_dir = screenshot_dir / vp["name"]
            vp_dir.mkdir(exist_ok=True)

            print(f"\n📱 Viewport: {vp['name']} ({vp['width']}x{vp['height']})")

            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                ignore_https_errors=True,
            )
            page = context.new_page()

            # Login
            print("  🔑 Logging in...")
            try:
                final_url = login(page)
                print(f"  ✅ Logged in → {final_url}")
            except Exception as e:
                print(f"  ❌ Login failed: {e}")
                browser.close()
                continue

            # Audit each route
            for idx, route in enumerate(ROUTES):
                name = safe_name(route)
                print(f"  [{idx+1}/{len(ROUTES)}] {route}...", end=" ", flush=True)

                before_count = len(all_issues)
                audit_route(page, route, vp_dir, all_issues)
                new_issues = len(all_issues) - before_count

                status = "✅" if new_issues == 0 else f"⚠️ {new_issues} issues"
                print(status)

            browser.close()

    # Generate report
    report = generate_report(all_issues, screenshot_dir, ts)
    report_path = f"audit-report-{ts}.md"
    with open(report_path, "w") as f:
        f.write(report)

    # Also save raw JSON
    json_path = f"audit-issues-{ts}.json"
    with open(json_path, "w") as f:
        json.dump(all_issues, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"📊 Report: {report_path}")
    print(f"📋 Raw data: {json_path}")
    print(f"📸 Screenshots: {screenshot_dir}/")
    print(f"\n🔍 Total issues: {len(all_issues)}")
    for sev in ['critical', 'high', 'medium', 'low']:
        count = len([i for i in all_issues if i['severity'] == sev])
        if count:
            emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🔵'}[sev]
            print(f"  {emoji} {sev.upper()}: {count}")

if __name__ == "__main__":
    main()
