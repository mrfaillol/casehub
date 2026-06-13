#!/usr/bin/env python3
"""
Client Mapping Manager - Manages CLIENT_MAPPING in email_processor.py
Provides read/write access to client-paralegal assignments for the CaseHub interface.
"""

import re
import ast
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
EMAIL_PROCESSOR_PATH = BASE_DIR / "email_processor.py"


def get_client_mapping() -> Dict[str, Dict[str, Any]]:
    """
    Read CLIENT_MAPPING from email_processor.py.
    Returns dict: {email: {name, paralegal, case}}
    """
    content = EMAIL_PROCESSOR_PATH.read_text()

    # Find CLIENT_MAPPING definition using a more robust pattern
    # Match from CLIENT_MAPPING = { to the closing }
    pattern = r"CLIENT_MAPPING\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        logger.error("CLIENT_MAPPING not found in email_processor.py")
        return {}

    try:
        # Parse the dict string
        dict_str = "{" + match.group(1) + "}"
        # Remove comments
        dict_str = re.sub(r'#.*$', '', dict_str, flags=re.MULTILINE)
        return ast.literal_eval(dict_str)
    except Exception as e:
        logger.error(f"Failed to parse CLIENT_MAPPING: {e}")
        return {}


def get_all_clients() -> List[Dict[str, Any]]:
    """Get all clients as a list for API response."""
    mapping = get_client_mapping()
    clients = []
    for email, info in mapping.items():
        clients.append({
            "email": email,
            "name": info.get("name", ""),
            "paralegal": info.get("paralegal", ""),
            "case": info.get("case", "")
        })
    return sorted(clients, key=lambda x: x["name"].lower())


def update_client(email: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a client in CLIENT_MAPPING.

    Args:
        email: Client email (key)
        updates: Fields to update (name, paralegal, case)

    Returns:
        Updated client dict
    """
    content = EMAIL_PROCESSOR_PATH.read_text()
    mapping = get_client_mapping()

    email_lower = email.lower()
    # Find the actual key (case-insensitive match)
    actual_key = None
    for key in mapping.keys():
        if key.lower() == email_lower:
            actual_key = key
            break

    if not actual_key:
        raise ValueError(f"Client not found: {email}")

    # Update the mapping in memory
    old_info = mapping[actual_key]
    new_info = {**old_info}

    # Apply updates
    if "paralegal" in updates:
        new_info["paralegal"] = updates["paralegal"]
    if "name" in updates:
        new_info["name"] = updates["name"]
    if "case" in updates:
        new_info["case"] = updates["case"]

    # Build the new entry line
    new_entry = f'    "{actual_key}": {{"name": "{new_info["name"]}", "paralegal": "{new_info["paralegal"]}", "case": "{new_info["case"]}"}}'

    # Find and replace the old entry
    # Pattern to match the specific email entry (with optional comment and trailing comma)
    old_pattern = rf'(\s*)"{re.escape(actual_key)}":\s*\{{"name":\s*"[^"]*",\s*"paralegal":\s*"[^"]*",\s*"case":\s*"[^"]*"\}},?(\s*#.*)?'

    def replacer(match):
        indent = match.group(1) or "    "
        comment = match.group(2) or ""
        # Check if there was a comma by looking at original match
        had_comma = "," in match.group(0).split("}")[1].split("#")[0] if "}" in match.group(0) else False
        comma = "," if had_comma else ""
        return f'{indent}"{actual_key}": {{"name": "{new_info["name"]}", "paralegal": "{new_info["paralegal"]}", "case": "{new_info["case"]}"}}{comma}{comment}'

    new_content = re.sub(old_pattern, replacer, content)

    if new_content == content:
        # Fallback: try simpler replacement
        logger.warning(f"Regex replacement failed, trying simpler approach for {actual_key}")
        # Just find and replace the specific line
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if f'"{actual_key}"' in line and 'name' in line:
                # Preserve indentation and trailing content
                indent = len(line) - len(line.lstrip())
                comment_match = re.search(r'(#.*)$', line)
                comment = comment_match.group(1) if comment_match else ""
                lines[i] = ' ' * indent + f'"{actual_key}": {{"name": "{new_info["name"]}", "paralegal": "{new_info["paralegal"]}", "case": "{new_info["case"]}"}},{comment}'
                break
        new_content = '\n'.join(lines)

    EMAIL_PROCESSOR_PATH.write_text(new_content)
    logger.info(f"Updated client {actual_key}: {updates}")

    return {"email": actual_key, **new_info}


def add_client(email: str, name: str, paralegal: str, case: str = "") -> Dict[str, Any]:
    """Add a new client to CLIENT_MAPPING."""
    content = EMAIL_PROCESSOR_PATH.read_text()
    mapping = get_client_mapping()

    email_lower = email.lower().strip()

    # Check if client already exists
    for existing_email in mapping.keys():
        if existing_email.lower() == email_lower:
            raise ValueError(f"Client already exists: {existing_email}")

    # Find the last entry in CLIENT_MAPPING and add new entry after it
    # Look for the pattern: "email": {...}, followed by # Add more clients
    pattern = r'(    "[\w@._-]+": \{[^}]+\},?)(\s*# Add more clients)'

    new_entry = f'    "{email_lower}": {{"name": "{name}", "paralegal": "{paralegal}", "case": "{case}"}},'

    def replacer(match):
        existing = match.group(1)
        comment = match.group(2)
        # Make sure existing entry has comma
        if not existing.rstrip().endswith(','):
            existing = existing.rstrip() + ','
        return f'{existing}\n{new_entry}\n{comment}'

    new_content = re.sub(pattern, replacer, content)

    if new_content == content:
        # Fallback: insert before closing brace
        logger.warning("Pattern not found, inserting before closing brace")
        # Find CLIENT_MAPPING closing brace
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == '}' and i > 0:
                # Check if previous line is part of CLIENT_MAPPING
                if 'CLIENT_MAPPING' in '\n'.join(lines[max(0,i-15):i]):
                    lines.insert(i, new_entry)
                    break
        new_content = '\n'.join(lines)

    EMAIL_PROCESSOR_PATH.write_text(new_content)
    logger.info(f"Added client {email_lower}")

    return {"email": email_lower, "name": name, "paralegal": paralegal, "case": case}


def remove_client(email: str) -> bool:
    """Remove a client from CLIENT_MAPPING."""
    content = EMAIL_PROCESSOR_PATH.read_text()
    mapping = get_client_mapping()

    email_lower = email.lower()
    actual_key = None
    for key in mapping.keys():
        if key.lower() == email_lower:
            actual_key = key
            break

    if not actual_key:
        raise ValueError(f"Client not found: {email}")

    # Remove the entry line
    pattern = rf'\s*"{re.escape(actual_key)}":\s*\{{[^}}]+\}},?\s*(?:#.*)?\n?'
    new_content = re.sub(pattern, '\n', content)

    # Clean up any double newlines that might result
    new_content = re.sub(r'\n\n\n+', '\n\n', new_content)

    EMAIL_PROCESSOR_PATH.write_text(new_content)
    logger.info(f"Removed client {actual_key}")

    return True


if __name__ == "__main__":
    # Test the module
    import json
    print("Testing client_mapping_manager...")

    clients = get_all_clients()
    print(f"\nFound {len(clients)} clients:")
    for c in clients:
        print(f"  - {c['name']} ({c['email']}) -> {c['paralegal']}")
