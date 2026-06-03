#!/usr/bin/env python3
"""
Email Automation Script - CaseHub
Runs email sync and Notion task creation automatically.
Should be called via cron every 5 minutes.
"""
import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.getenv('LOG_DIR', '/var/log/casehub'))
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'email_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Change to casehub directory
_base_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_base_dir)
sys.path.insert(0, _base_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("ERROR: DATABASE_URL not set. Export it or create .env")
    sys.exit(1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def sync_emails():
    """Sync emails from IMAP for all enabled accounts."""
    from services.email_service import email_service
    
    db = SessionLocal()
    try:
        # Get enabled email accounts
        result = db.execute(text('SELECT id, email_address FROM email_accounts WHERE enabled = TRUE'))
        accounts = result.fetchall()
        
        for account in accounts:
            logger.info(f'Syncing emails for account {account[1]}...')
            try:
                # Call the sync function directly
                from routes.emails import sync_emails_from_account
                # Sincronizar INBOX e All Mail para pegar emails arquivados/filtrados
                folders = ['INBOX', '[Gmail]/All Mail']
                for folder in folders:
                    try:
                        sync_emails_from_account(account[0], folder, limit=100)
                    except Exception as fe:
                        logger.warning(f'Error syncing {folder}: {fe}')
                logger.info(f'Sync completed for {account[1]}')
            except Exception as e:
                logger.error(f'Error syncing {account[1]}: {e}')
    finally:
        db.close()


async def process_emails():
    """Process pending emails and create Notion tasks."""
    from services.email_worker import EmailWorker
    
    db = SessionLocal()
    try:
        worker = EmailWorker(db)
        results = await worker.run_once()
        
        logger.info(f'Worker results: {results["processed"]} processed, {results["tasks_created"]} tasks created')
        
        if results['errors']:
            for err in results['errors']:
                logger.error(f'Worker error: {err}')
        
        return results
    finally:
        db.close()


def main():
    logger.info('=' * 50)
    logger.info('Email Automation starting...')
    
    try:
        # Step 1: Sync emails from IMAP
        logger.info('Step 1: Syncing emails from IMAP...')
        sync_emails()
        
        # Step 2: Process pending emails (create Notion tasks)
        logger.info('Step 2: Processing pending emails...')
        results = asyncio.run(process_emails())
        
        logger.info('Email Automation completed successfully')
        return 0
        
    except Exception as e:
        logger.error(f'Email Automation failed: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
