#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle

SCOPES = ["https://www.googleapis.com/auth/drive"]
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(_BASE_DIR, "google_drive_credentials.json")
TOKEN_PATH = os.path.join(_BASE_DIR, "google_drive_token.pickle")

print("=" * 80)
print("GOOGLE DRIVE - COMPLETAR AUTORIZAÇÃO")
print("=" * 80)
print()

# Create new flow
flow = InstalledAppFlow.from_client_secrets_file(
    CREDENTIALS_PATH, 
    SCOPES,
    redirect_uri="urn:ietf:wg:oauth:2.0:oob"
)

# Get auth URL (just to initialize flow state)
_, _ = flow.authorization_url(prompt="consent")

# Ask for code
code = input("Cole o código de autorização aqui: ").strip()

if not code:
    print("❌ Código vazio. Abortando.")
    sys.exit(1)

try:
    # Exchange code for credentials
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    # Save token
    with open(TOKEN_PATH, "wb") as token:
        pickle.dump(creds, token)
    
    print(f"\n✅ Autorização completa!")
    print(f"   Token salvo: {TOKEN_PATH}")
    
    # Test connection
    service = build("drive", "v3", credentials=creds)
    about = service.about().get(fields="user(emailAddress)").execute()
    email = about.get("user", {}).get("emailAddress")
    
    print(f"   Conectado como: {email}")
    
    # Test access to Active Clients
    results = service.files().list(
        q="name=Active Clients and mimeType=application/vnd.google-apps.folder and trashed=false",
        fields="files(id, name)",
        pageSize=10
    ).execute()
    
    folders = results.get("files", [])
    if len(folders) > 0:
        print(f"\n🎉 SUCCESS! Agora consegue ver 'Active Clients'!")
        print(f"   Folder ID: {folders[0].get('id')}")
    else:
        print(f"\n⚠️  Ainda não vê 'Active Clients'")
        print(f"   Verifique ownership da pasta")
    
except Exception as e:
    print(f"\n❌ Erro: {e}")
    sys.exit(1)

print("\n✅ Pronto! Execute 'pm2 restart casehub' para aplicar")
print("=" * 80)
