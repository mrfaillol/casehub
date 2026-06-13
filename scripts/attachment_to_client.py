#!/usr/bin/env python3
"""
Attachment to Client Folder Handler
Saves email attachments directly to client folders in /documents/clients/
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import unicodedata

logger = logging.getLogger(__name__)

# Base path for client documents
CLIENTS_BASE = Path(os.environ.get('CASEHUB_DOCS_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'documents', 'clients')))

# Document type to subfolder mapping
DOC_TYPE_FOLDERS = {
    'Passport': 'Personal Documents',
    'I-94 Travel Record': 'Personal Documents',
    'Visa': 'Personal Documents',
    'Visa Stamp': 'Personal Documents',
    'EAD Card': 'Personal Documents',
    'Green Card': 'Personal Documents',
    'Birth Certificate': 'Personal Documents',
    'Marriage Certificate': 'Personal Documents',
    'Photo': 'Personal Documents',
    'Diploma': 'Education',
    'Academic Transcript': 'Education',
    'Credential Evaluation': 'Education',
    'Resume/CV': 'Employment',
    'Employment Letter': 'Employment',
    'Employment Contract': 'Employment',
    'Pay Stub': 'Employment',
    'Tax Return': 'Employment',
    'Financial Statement': 'Employment',
    'Bank Statement': 'Employment',
    'Letter of Recommendation': 'Letters of Recommendation',
    'Publication': 'Evidence - Publications',
    'Citation': 'Evidence - Citations',
    'Award/Recognition': 'Evidence - Awards',
    'Media Coverage': 'Evidence - Media',
    'Professional Membership': 'Evidence - Memberships',
    'USCIS Form': 'USCIS Forms',
    'Receipt Notice': 'USCIS Forms',
    'Request for Evidence': 'USCIS Forms',
    'Approval Notice': 'USCIS Forms',
    'Supporting Evidence': 'Evidence',
    'Other Document': 'Other Documents',
}


def normalize_string(s: str) -> str:
    """Remove accents and convert to lowercase for comparison."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', s)
    s = s.encode('ASCII', 'ignore').decode('ASCII')
    return s.lower()


def _tokenize_folder_name(folder_name: str) -> set:
    """Split folder name into normalized word tokens for matching."""
    tokens = re.split(r'[\s,\-_\.]+', folder_name)
    return {normalize_string(t) for t in tokens if len(t) > 2}


def find_client_folder(client_name: str, client_email: str = None) -> Optional[Path]:
    """
    Find the client folder by name or email.

    Uses word-level matching (not substring) to prevent cross-client
    contamination. Requires multiple matching tokens when available.
    """
    if not CLIENTS_BASE.exists():
        logger.error(f'Client base folder not found: {CLIENTS_BASE}')
        return None

    # Prepare search terms from name
    name_parts = [normalize_string(p) for p in client_name.strip().split() if len(p) > 2]

    # Add email parts if available
    email_parts = []
    if client_email:
        local_part = client_email.split('@')[0] if '@' in client_email else client_email
        email_parts = [normalize_string(p) for p in re.split(r'[._-]', local_part) if len(p) > 2]

    all_search_terms = set(name_parts + email_parts)

    if not all_search_terms:
        logger.warning(f'No valid search terms for client: {client_name}')
        return None

    best_match = None
    best_score = 0

    # Minimum score: require at least 2 token matches when we have multiple terms
    min_score = 2 if len(name_parts) >= 2 else 1

    for folder in CLIENTS_BASE.iterdir():
        if not folder.is_dir():
            continue

        if folder.name.startswith('_') or folder.name in ['CLOSED', 'STANDBY', 'template', 'z']:
            continue

        folder_tokens = _tokenize_folder_name(folder.name)

        # Word-level exact matching (not substring)
        matches = len(all_search_terms & folder_tokens)

        if matches > best_score:
            best_score = matches
            best_match = folder

    if best_match and best_score >= min_score:
        logger.info(f'Matched client "{client_name}" to folder "{best_match.name}" (score: {best_score}/{len(all_search_terms)})')
        return best_match

    if best_match and best_score > 0:
        logger.warning(f'Weak match for "{client_name}" → "{best_match.name}" (score: {best_score}, need {min_score}). Skipping.')

    logger.warning(f'No folder found for client: {client_name} (email: {client_email})')
    return None


def get_subfolder_for_type(doc_type: str) -> str:
    """Get the subfolder name for a document type."""
    return DOC_TYPE_FOLDERS.get(doc_type, 'Other Documents')


def save_to_client_folder(
    content: bytes,
    filename: str,
    client_name: str,
    doc_type: str,
    client_email: str = None
) -> Dict:
    """
    Save attachment to client folder.
    
    Args:
        content: File content bytes
        filename: Original filename
        client_name: Client name
        doc_type: Classified document type
        client_email: Client email (optional, helps find folder)
        
    Returns:
        Dict with success status and path
    """
    # Find client folder
    client_folder = find_client_folder(client_name, client_email)
    
    if not client_folder:
        # Create folder based on client name
        parts = client_name.strip().split()
        if len(parts) >= 2:
            last = parts[-1].upper()
            first = ' '.join(parts[:-1]).title()
            folder_name = f'{last}, {first} - UNKNOWN'
        else:
            folder_name = f'{client_name.upper()} - UNKNOWN'
        
        client_folder = CLIENTS_BASE / folder_name
        client_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f'Created new client folder: {client_folder}')
    
    # Get subfolder for document type
    subfolder_name = get_subfolder_for_type(doc_type)
    target_folder = client_folder / subfolder_name
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Build target path
    target_path = target_folder / filename
    
    # Handle duplicates
    counter = 1
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    while target_path.exists():
        target_path = target_folder / f'{stem}_{counter}{suffix}'
        counter += 1
    
    # Save file
    try:
        with open(target_path, 'wb') as f:
            f.write(content)
        
        logger.info(f'Saved to client folder: {target_path}')
        
        return {
            'success': True,
            'path': str(target_path),
            'client_folder': str(client_folder),
            'subfolder': subfolder_name,
            'filename': target_path.name
        }
    
    except Exception as e:
        logger.error(f'Error saving to client folder: {e}')
        return {
            'success': False,
            'error': str(e)
        }


def classify_by_filename(filename: str) -> str:
    """Simple classification based on filename patterns."""
    fn_lower = filename.lower()
    
    if 'passport' in fn_lower or 'passaporte' in fn_lower:
        return 'Passport'
    elif 'i-94' in fn_lower or 'i94' in fn_lower:
        return 'I-94'
    elif 'visa' in fn_lower:
        return 'Visa'
    elif 'ead' in fn_lower:
        return 'EAD Card'
    elif 'green card' in fn_lower or 'greencard' in fn_lower:
        return 'Green Card'
    elif 'birth' in fn_lower or 'nascimento' in fn_lower:
        return 'Birth Certificate'
    elif 'marriage' in fn_lower or 'casamento' in fn_lower:
        return 'Marriage Certificate'
    elif 'photo' in fn_lower or 'foto' in fn_lower:
        return 'Photo'
    elif 'diploma' in fn_lower:
        return 'Diploma'
    elif 'transcript' in fn_lower or 'historico' in fn_lower:
        return 'Transcript'
    elif 'resume' in fn_lower or 'cv' in fn_lower or 'curriculo' in fn_lower:
        return 'Resume'
    elif 'lor' in fn_lower or 'recommendation' in fn_lower or 'recomenda' in fn_lower:
        return 'Recommendation Letter'
    elif 'tax' in fn_lower or 'imposto' in fn_lower:
        return 'Tax Return'
    elif 'pay stub' in fn_lower or 'paystub' in fn_lower:
        return 'Pay Stub'
    elif 'bank' in fn_lower or 'extrato' in fn_lower:
        return 'Bank Statement'
    elif 'employment' in fn_lower or 'emprego' in fn_lower:
        return 'Employment Letter'
    elif 'publication' in fn_lower or 'paper' in fn_lower or 'artigo' in fn_lower:
        return 'Publication'
    elif 'award' in fn_lower or 'premio' in fn_lower:
        return 'Award'
    elif 'i-' in fn_lower and any(c.isdigit() for c in fn_lower):
        return 'USCIS Form'
    elif 'receipt' in fn_lower or 'recibo' in fn_lower:
        return 'Receipt Notice'
    elif 'rfe' in fn_lower:
        return 'RFE'
    elif 'approval' in fn_lower or 'aprovacao' in fn_lower:
        return 'Approval Notice'
    else:
        return 'Other Document'


if __name__ == '__main__':
    # Test
    print('Testing folder search...')
    
    folder = find_client_folder('Klaudio de Oliveira', 'klaudio.marcondes@gmail.com')
    print(f'Klaudio: {folder}')
    
    folder2 = find_client_folder('Omar Abdelmotelb', 'omaressam.int@gmail.com')
    print(f'Omar: {folder2}')
    
    folder3 = find_client_folder('Nuttapon Pratyapattanapong', 'np.pratya@gmail.com')
    print(f'Nuttapon: {folder3}')
