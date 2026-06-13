#!/usr/bin/env python3
"""
Cria clientes para pastas que não têm match no banco.
"""

import os
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from unidecode import unidecode

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: DATABASE_URL not set. Export it or create .env")
    sys.exit(1)

def normalize_name(name):
    return re.sub(r'[^a-z0-9]', '', unidecode(name).lower())

def extract_client_from_path(file_path):
    match = re.search(r'/documents/clients/([^/]+)/', file_path)
    if match:
        return match.group(1)
    return None

def parse_folder_to_client(folder):
    """
    Parse folder name to create client.
    Returns (first_name, last_name)
    """
    folder = folder.strip()
    
    # Skip special folders
    skip_folders = ['closed', 'copy', 'standby', 'template', 'z', 'unknown']
    if any(s in folder.lower() for s in skip_folders):
        return None, None
    
    # Format: SOBRENOME, Nome - VISA
    if ',' in folder:
        name_part = folder.split(' - ')[0] if ' - ' in folder else folder
        parts = name_part.split(',')
        if len(parts) >= 2:
            last_name = parts[0].strip().title()
            first_name = parts[1].strip().title()
            return first_name, last_name
    
    # Format: sobrenome-nome (slugified)
    parts = folder.replace('_', '-').split('-')
    if len(parts) >= 2:
        # Assume format is lastname-firstname
        last_name = parts[0].strip().title()
        first_name = ' '.join(parts[1:]).strip().title()
        return first_name, last_name
    
    # Single name - use as last name
    return 'Unknown', folder.strip().title()

def client_exists(conn, first_name, last_name):
    """Check if client already exists"""
    first_norm = normalize_name(first_name)
    last_norm = normalize_name(last_name)
    
    result = conn.execute(text('''
        SELECT id FROM clients
        WHERE LOWER(REGEXP_REPLACE(unaccent(first_name), '[^a-z0-9]', '', 'g')) = :first
        AND LOWER(REGEXP_REPLACE(unaccent(last_name), '[^a-z0-9]', '', 'g')) = :last
    '''), {'first': first_norm, 'last': last_norm}).fetchone()
    
    return result is not None

def create_missing_clients():
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        # Enable unaccent extension
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS unaccent'))
        
        # Get all unique folder names from documents without client_id
        folders = conn.execute(text('''
            SELECT DISTINCT 
                SUBSTRING(file_path FROM '/documents/clients/([^/]+)/') as folder
            FROM documents 
            WHERE client_id IS NULL 
            AND file_path LIKE '%/documents/clients/%'
        ''')).fetchall()
        
        print(f'Pastas sem match: {len(folders)}')
        
        created = 0
        skipped = []
        
        for row in folders:
            folder = row.folder
            if not folder:
                continue
            
            first_name, last_name = parse_folder_to_client(folder)
            
            if not first_name or not last_name:
                skipped.append(f'{folder} (skip folder)')
                continue
            
            # Check if client exists
            try:
                exists = client_exists(conn, first_name, last_name)
            except:
                exists = False
            
            if not exists:
                conn.execute(text('''
                    INSERT INTO clients (first_name, last_name, status, created_at)
                    VALUES (:first, :last, 'pending_review', NOW())
                '''), {'first': first_name, 'last': last_name})
                print(f'  Criado: {first_name} {last_name}')
                created += 1
            else:
                skipped.append(f'{folder} (ja existe)')
        
        conn.commit()
        
        print(f'')
        print(f'=== RESULTADO ===')
        print(f'Clientes criados: {created}')
        print(f'Skipped: {len(skipped)}')

if __name__ == '__main__':
    create_missing_clients()
