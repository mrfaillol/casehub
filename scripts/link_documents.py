#!/usr/bin/env python3
"""
Vincula documentos existentes aos clientes cadastrados no CaseHub.
Extrai nome do cliente do file_path e faz matching com a tabela clients.
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
    """Normaliza nome para comparação (remove acentos, lowercase, só alfanum)"""
    return re.sub(r'[^a-z0-9]', '', unidecode(name).lower())

def extract_client_from_path(file_path):
    """Extrai nome do cliente do file_path"""
    match = re.search(r'/documents/clients/([^/]+)/', file_path)
    if match:
        return match.group(1)
    return None

def parse_folder_name(folder):
    """
    Parse folder name to extract client name parts.
    Handles both formats:
    - 'SOBRENOME, Nome - VISA' -> (sobrenome, nome)
    - 'sobrenome-nome' -> (sobrenome, nome)
    """
    folder = folder.strip()
    
    # Format: SOBRENOME, Nome - VISA
    if ',' in folder:
        # Remove visa part
        name_part = folder.split(' - ')[0] if ' - ' in folder else folder
        parts = name_part.split(',')
        if len(parts) >= 2:
            last_name = parts[0].strip()
            first_name = parts[1].strip()
            return normalize_name(last_name), normalize_name(first_name)
    
    # Format: sobrenome-nome or nome-sobrenome (slugified)
    parts = folder.replace('_', '-').split('-')
    if len(parts) >= 2:
        return normalize_name(parts[0]), normalize_name('-'.join(parts[1:]))
    
    # Single name
    return normalize_name(folder), ''

def link_documents():
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        # 1. Get all clients and create index
        clients = conn.execute(text('''
            SELECT id, first_name, last_name FROM clients
        ''')).fetchall()
        
        print(f'Total clientes no banco: {len(clients)}')
        
        # Create index with multiple variations
        client_index = {}
        for c in clients:
            cid, first, last = c
            first_norm = normalize_name(first or '')
            last_norm = normalize_name(last or '')
            
            # Various combinations
            variations = [
                f'{last_norm}{first_norm}',
                f'{first_norm}{last_norm}',
                f'{last_norm}-{first_norm}',
                f'{first_norm}-{last_norm}',
                last_norm,  # Just last name for partial match
            ]
            
            for v in variations:
                if v and len(v) > 2:
                    if v not in client_index:
                        client_index[v] = cid
        
        print(f'Index de clientes criado: {len(client_index)} variações')
        
        # 2. Get all documents without client_id
        docs = conn.execute(text('''
            SELECT id, file_path, name FROM documents
            WHERE client_id IS NULL AND file_path IS NOT NULL
        ''')).fetchall()
        
        print(f'Documentos sem client_id: {len(docs)}')
        
        # 3. Match and update
        updated = 0
        not_found = set()
        
        for doc in docs:
            doc_id, file_path, name = doc
            folder = extract_client_from_path(file_path)
            
            if not folder:
                continue
            
            # Parse folder name
            part1, part2 = parse_folder_name(folder)
            
            # Try to find match
            client_id = None
            
            # Try full combination
            combined = f'{part1}{part2}'
            if combined in client_index:
                client_id = client_index[combined]
            elif f'{part2}{part1}' in client_index:
                client_id = client_index[f'{part2}{part1}']
            elif part1 in client_index:
                client_id = client_index[part1]
            elif part2 and part2 in client_index:
                client_id = client_index[part2]
            
            if client_id:
                conn.execute(text('''
                    UPDATE documents SET client_id = :client_id WHERE id = :doc_id
                '''), {'client_id': client_id, 'doc_id': doc_id})
                updated += 1
            else:
                not_found.add(folder)
        
        conn.commit()
        
        print(f'')
        print(f'=== RESULTADO ===')
        print(f'Documentos vinculados: {updated}')
        print(f'Pastas sem match ({len(not_found)}):')
        for f in sorted(not_found)[:20]:
            print(f'  - {f}')
        if len(not_found) > 20:
            print(f'  ... e mais {len(not_found) - 20}')

def link_to_cases():
    """Vincula documentos aos casos dos clientes"""
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        result = conn.execute(text('''
            UPDATE documents d
            SET case_id = (
                SELECT c.id FROM cases c WHERE c.client_id = d.client_id LIMIT 1
            )
            WHERE d.client_id IS NOT NULL AND d.case_id IS NULL
        '''))
        conn.commit()
        print(f'Documentos vinculados a casos: {result.rowcount}')

def update_visa_category():
    """Atualiza visa_category baseado no caso"""
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        result = conn.execute(text('''
            UPDATE documents d
            SET visa_category = c.visa_type
            FROM cases c
            WHERE d.case_id = c.id AND d.visa_category IS NULL
        '''))
        conn.commit()
        print(f'Visa category atualizado: {result.rowcount}')

if __name__ == '__main__':
    print('=== VINCULANDO DOCUMENTOS A CLIENTES ===')
    link_documents()
    print('')
    print('=== VINCULANDO DOCUMENTOS A CASOS ===')
    link_to_cases()
    print('')
    print('=== ATUALIZANDO VISA CATEGORY ===')
    update_visa_category()
