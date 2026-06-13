#!/usr/bin/env python3
"""
Google Drive Handler - CaseHub
Handles uploading documents to Google Drive with organized folder structure.
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_DRIVE_CREDENTIALS_PATH",
    "/Users/beijaflor/Projects_Local/CREDENTIALS/google_drive_credentials.json"
)
TOKEN_PATH = os.getenv(
    "GOOGLE_DRIVE_TOKEN_PATH",
    "/Users/beijaflor/Projects_Local/PROJECTS/02_immigration-law-suite/ilc-case-management/google_drive_token.pickle"
)
ROOT_FOLDER_NAME = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER", "CaseHub Clients")

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Folder structure by visa category
VISA_FOLDER_STRUCTURE = {
    "EB1A": [
        "Documentos Pessoais",
        "Premios e Reconhecimentos",
        "Publicacoes",
        "Citacoes",
        "Midia",
        "Membership",
        "Lideranca",
        "Contribuicoes Originais",
        "Cartas de Recomendacao",
        "USCIS"
    ],
    "EB2-NIW": [
        "Documentos Pessoais",
        "Diplomas e Certificados",
        "Evidencias",
        "Cartas de Recomendacao",
        "Plano de Trabalho",
        "USCIS"
    ],
    "General": [
        "Documentos Pessoais",
        "Outros"
    ]
}

# Map document types to subfolders
DOCUMENT_TYPE_TO_FOLDER = {
    "Passaporte": "Documentos Pessoais",
    "I-94": "Documentos Pessoais",
    "Visa": "Documentos Pessoais",
    "EAD Card": "Documentos Pessoais",
    "Green Card": "Documentos Pessoais",
    "Birth Certificate": "Documentos Pessoais",
    "Marriage Certificate": "Documentos Pessoais",
    "Diploma": "Diplomas e Certificados",
    "Transcript": "Diplomas e Certificados",
    "Employment Letter": "Evidencias",
    "Tax Return": "Evidencias",
    "Pay Stub": "Evidencias",
    "Bank Statement": "Evidencias",
    "Recommendation Letter": "Cartas de Recomendacao",
    "Evidence": "Evidencias",
    "USCIS Form": "USCIS",
    "Receipt Notice": "USCIS",
    "Approval Notice": "USCIS",
    "RFE": "USCIS",
    "Outro": "Outros"
}

# EB1A specific mappings
EB1A_DOCUMENT_FOLDERS = {
    "Award": "Premios e Reconhecimentos",
    "Publication": "Publicacoes",
    "Citation": "Citacoes",
    "Media": "Midia",
    "Membership": "Membership",
    "Leadership": "Lideranca",
    "Contribution": "Contribuicoes Originais"
}


def get_drive_service():
    """
    Authenticate and return Google Drive service object.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("Google API packages not installed. Run: pip install google-api-python-client google-auth-oauthlib")
        return None

    creds = None

    # Load existing token
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Credentials file not found: {CREDENTIALS_PATH}")
                logger.info("Download credentials from Google Cloud Console and save to this path")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(
                port=8080,
                login_hint=os.getenv("ORG_EMAIL", "info@casehub.app"),
            )

        # Save token for future use
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    return build('drive', 'v3', credentials=creds)


class GoogleDriveHandler:
    """Handles Google Drive operations for document management."""

    def __init__(self):
        self.service = get_drive_service()
        self._folder_cache: Dict[str, str] = {}  # path -> folder_id
        self._root_folder_id: Optional[str] = None

    def is_connected(self) -> bool:
        """Check if Drive service is available."""
        return self.service is not None

    def get_root_folder_id(self) -> Optional[str]:
        """Get or create the root folder for CaseHub clients."""
        if self._root_folder_id:
            return self._root_folder_id

        if not self.service:
            return None

        try:
            # Search for existing folder
            query = f"name='{ROOT_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if files:
                self._root_folder_id = files[0]['id']
            else:
                # Create root folder
                file_metadata = {
                    'name': ROOT_FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                self._root_folder_id = folder.get('id')
                logger.info(f"Created root folder: {ROOT_FOLDER_NAME}")

            return self._root_folder_id

        except Exception as e:
            logger.error(f"Error getting root folder: {e}")
            return None

    def get_or_create_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        """
        Get existing folder or create new one.

        Args:
            folder_name: Name of the folder
            parent_id: Parent folder ID

        Returns:
            Folder ID or None on error
        """
        cache_key = f"{parent_id}/{folder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        if not self.service:
            return None

        try:
            # Search for existing folder
            query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if files:
                folder_id = files[0]['id']
            else:
                # Create folder
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]
                }
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = folder.get('id')
                logger.info(f"Created folder: {folder_name}")

            self._folder_cache[cache_key] = folder_id
            return folder_id

        except Exception as e:
            logger.error(f"Error creating folder {folder_name}: {e}")
            return None

    def get_client_folder(self, client_name: str) -> Optional[str]:
        """
        Get or create client's main folder.

        Args:
            client_name: Client's full name

        Returns:
            Folder ID or None
        """
        root_id = self.get_root_folder_id()
        if not root_id:
            return None

        return self.get_or_create_folder(client_name, root_id)

    def get_document_folder(
        self,
        client_name: str,
        visa_category: str = "General",
        document_type: str = "Outro"
    ) -> Optional[str]:
        """
        Get the appropriate folder for a document based on client, visa category, and document type.

        Structure: CaseHub Clients / {Client Name} / {Visa Category} / {Document Subfolder}

        Args:
            client_name: Client's full name
            visa_category: "EB1A", "EB2-NIW", or "General"
            document_type: Document type for subfolder selection

        Returns:
            Folder ID where document should be uploaded
        """
        # Get client folder
        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id:
            return None

        # Get visa category folder
        visa_folder_id = self.get_or_create_folder(visa_category, client_folder_id)
        if not visa_folder_id:
            return client_folder_id  # Fallback to client folder

        # Determine subfolder based on document type
        subfolder_name = DOCUMENT_TYPE_TO_FOLDER.get(document_type, "Outros")

        # Get or create subfolder
        subfolder_id = self.get_or_create_folder(subfolder_name, visa_folder_id)

        return subfolder_id or visa_folder_id

    def upload_document(
        self,
        file_path: str,
        client_name: str,
        document_title: str = None,
        visa_category: str = "General",
        document_type: str = "Outro",
        mime_type: str = None
    ) -> Dict[str, Any]:
        """
        Upload a document to Google Drive with proper folder organization.

        Args:
            file_path: Local path to the file
            client_name: Client's name for folder structure
            document_title: Title for the file (defaults to original filename)
            visa_category: "EB1A", "EB2-NIW", or "General"
            document_type: Document type for subfolder
            mime_type: MIME type of the file

        Returns:
            Dict with upload result including file ID and web link
        """
        result = {
            "success": False,
            "file_id": None,
            "web_link": None,
            "error": None
        }

        if not self.service:
            result["error"] = "Google Drive service not connected"
            return result

        file_path = Path(file_path)
        if not file_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result

        # Get destination folder
        folder_id = self.get_document_folder(client_name, visa_category, document_type)
        if not folder_id:
            result["error"] = "Could not determine destination folder"
            return result

        # Prepare file metadata
        file_name = document_title or file_path.name
        if not file_name.endswith(file_path.suffix):
            file_name += file_path.suffix

        # Detect MIME type if not provided
        if not mime_type:
            mime_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.txt': 'text/plain'
            }
            mime_type = mime_types.get(file_path.suffix.lower(), 'application/octet-stream')

        try:
            from googleapiclient.http import MediaFileUpload

            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }

            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            result["success"] = True
            result["file_id"] = file.get('id')
            result["web_link"] = file.get('webViewLink')
            result["download_link"] = file.get('webContentLink')

            logger.info(f"Uploaded to Drive: {file_name} -> {result['web_link']}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Upload failed: {e}")

        return result

    def create_client_folder_structure(
        self,
        client_name: str,
        visa_category: str = "EB2-NIW"
    ) -> Dict[str, str]:
        """
        Create complete folder structure for a new client.

        Args:
            client_name: Client's full name
            visa_category: Primary visa category

        Returns:
            Dict mapping folder names to their IDs
        """
        folders = {}

        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id:
            return folders

        folders["root"] = client_folder_id

        # Create visa category folder
        visa_folder_id = self.get_or_create_folder(visa_category, client_folder_id)
        if visa_folder_id:
            folders[visa_category] = visa_folder_id

            # Create subfolders for this visa category
            subfolders = VISA_FOLDER_STRUCTURE.get(visa_category, ["Outros"])
            for subfolder_name in subfolders:
                subfolder_id = self.get_or_create_folder(subfolder_name, visa_folder_id)
                if subfolder_id:
                    folders[f"{visa_category}/{subfolder_name}"] = subfolder_id

        return folders

    def list_client_documents(self, client_name: str) -> List[Dict[str, Any]]:
        """
        List all documents for a client.

        Args:
            client_name: Client's full name

        Returns:
            List of document metadata dicts
        """
        documents = []

        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id or not self.service:
            return documents

        try:
            # Recursive search in client folder
            query = f"'{client_folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, webViewLink, createdTime, size)'
            ).execute()

            for file in results.get('files', []):
                documents.append({
                    "id": file['id'],
                    "name": file['name'],
                    "mime_type": file['mimeType'],
                    "link": file.get('webViewLink'),
                    "created": file.get('createdTime'),
                    "size": file.get('size')
                })

        except Exception as e:
            logger.error(f"Error listing documents: {e}")

        return documents


def check_drive_connection() -> Dict[str, Any]:
    """Check Google Drive connection status."""
    result = {
        "connected": False,
        "credentials_path": CREDENTIALS_PATH,
        "token_path": TOKEN_PATH,
        "credentials_exist": os.path.exists(CREDENTIALS_PATH),
        "token_exist": os.path.exists(TOKEN_PATH),
        "error": None
    }

    handler = GoogleDriveHandler()

    if handler.is_connected():
        result["connected"] = True
        root_id = handler.get_root_folder_id()
        result["root_folder_id"] = root_id
    else:
        result["error"] = "Could not connect to Google Drive"

    return result


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Google Drive Handler - CaseHub")
    print("=" * 50)

    # Check connection
    print("\nChecking Google Drive connection...")
    status = check_drive_connection()

    print(f"  Credentials file: {status['credentials_path']}")
    print(f"    Exists: {status['credentials_exist']}")
    print(f"  Token file: {status['token_path']}")
    print(f"    Exists: {status['token_exist']}")
    print(f"  Connected: {status['connected']}")

    if status['connected']:
        print(f"  Root folder ID: {status.get('root_folder_id')}")
    else:
        print(f"  Error: {status.get('error')}")

        if not status['credentials_exist']:
            print("\nTo setup Google Drive:")
            print("1. Go to Google Cloud Console")
            print("2. Create a project and enable Drive API")
            print("3. Create OAuth 2.0 credentials (Desktop app)")
            print(f"4. Download and save to: {CREDENTIALS_PATH}")

    # Test upload if file provided
    if len(sys.argv) > 2 and status['connected']:
        test_file = sys.argv[1]
        client_name = sys.argv[2]

        print(f"\nUploading test file: {test_file}")
        print(f"Client: {client_name}")

        handler = GoogleDriveHandler()
        result = handler.upload_document(
            file_path=test_file,
            client_name=client_name,
            visa_category="EB2-NIW",
            document_type="Evidence"
        )

        if result["success"]:
            print(f"Success! Link: {result['web_link']}")
        else:
            print(f"Failed: {result['error']}")
    elif len(sys.argv) == 1:
        print("\nUsage: python google_drive_handler.py [file_path] [client_name]")
