"""
Google Calendar Integration - CaseHub
Verifica disponibilidade do Daniel (Attorney)

Uso:
    python google_calendar.py --setup     # Primeira vez: autenticar
    python google_calendar.py --check     # Verificar disponibilidade
    python google_calendar.py --week      # Ver agenda da semana
"""

import os
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    raise ImportError(
        "Required packages not installed. Run: "
        "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
    )

# Configuração
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]

# Caminhos
BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "google_calendar_token.pickle"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "google_calendar_credentials.json"

# Configuração do Daniel
DANIEL_CONFIG = {
    "available_days": [2, 3],  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    "available_hours": {
        "start": 11,  # 11 AM EST
        "end": 14     # 2 PM EST (exclusive)
    },
    "meeting_duration_minutes": 30,
    "timezone": "America/New_York"
}


def create_client_secret_file():
    """Cria arquivo de credenciais OAuth a partir do credentials.json consolidado"""

    # Ler credenciais consolidadas
    with open(CREDENTIALS_DIR / "credentials.json", "r") as f:
        all_creds = json.load(f)

    # Usar api_1 (ou criar nova entrada para calendar)
    oauth_creds = all_creds.get("google_oauth2", {}).get("api_1", {})

    if not oauth_creds:
        print("❌ Credenciais OAuth não encontradas em credentials.json")
        return False

    # Formato esperado pelo Google
    client_secret = {
        "installed": {
            "client_id": oauth_creds["client_id"],
            "client_secret": oauth_creds["client_secret"],
            "redirect_uris": oauth_creds.get("redirect_uris", ["http://localhost"]),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    # Salvar
    with open(CLIENT_SECRET_FILE, "w") as f:
        json.dump(client_secret, f, indent=2)

    print(f"✅ Arquivo de credenciais criado: {CLIENT_SECRET_FILE}")
    return True


def authenticate():
    """Autenticar com Google Calendar API"""
    creds = None

    # Verificar token existente
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    # Se não há credenciais válidas, autenticar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Renovando token...")
            creds.refresh(Request())
        else:
            # Criar arquivo de credenciais se não existir
            if not CLIENT_SECRET_FILE.exists():
                if not create_client_secret_file():
                    return None

            print("🔐 Abrindo navegador para autenticação...")
            print(f"   Use a conta: info@casehub.app ou center@casehub.app")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE),
                SCOPES
            )
            creds = flow.run_local_server(port=8080)

        # Salvar token
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
        print(f"✅ Token salvo: {TOKEN_FILE}")

    return creds


def get_calendar_service():
    """Obter serviço do Google Calendar"""
    creds = authenticate()
    if not creds:
        return None

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except HttpError as error:
        print(f"❌ Erro ao conectar: {error}")
        return None


def get_events(days_ahead=7, calendar_id='primary'):
    """Buscar eventos dos próximos dias"""
    service = get_calendar_service()
    if not service:
        return []

    now = datetime.utcnow()
    time_min = now.isoformat() + 'Z'
    time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return events

    except HttpError as error:
        print(f"❌ Erro ao buscar eventos: {error}")
        return []


def get_daniel_availability(days_ahead=7):
    """
    Verificar disponibilidade do Daniel nos próximos dias
    Retorna slots disponíveis baseado nas regras:
    - Apenas Quarta e Quinta
    - 11 AM - 2 PM EST (13h - 16h Brasil)
    - Slots de 30 minutos
    """

    events = get_events(days_ahead)

    # Criar lista de slots ocupados
    busy_slots = []
    for event in events:
        start = event.get('start', {}).get('dateTime')
        end = event.get('end', {}).get('dateTime')
        if start and end:
            busy_slots.append({
                'start': datetime.fromisoformat(start.replace('Z', '+00:00')),
                'end': datetime.fromisoformat(end.replace('Z', '+00:00')),
                'summary': event.get('summary', 'Busy')
            })

    # Gerar slots disponíveis
    available_slots = []
    now = datetime.now()

    for day_offset in range(days_ahead):
        check_date = now + timedelta(days=day_offset)

        # Verificar se é Quarta (2) ou Quinta (3)
        if check_date.weekday() not in DANIEL_CONFIG["available_days"]:
            continue

        # Gerar slots de 30 min entre 11 AM e 2 PM EST
        for hour in range(DANIEL_CONFIG["available_hours"]["start"],
                         DANIEL_CONFIG["available_hours"]["end"]):
            for minute in [0, 30]:
                slot_start = check_date.replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )
                slot_end = slot_start + timedelta(minutes=30)

                # Pular slots no passado
                if slot_start <= now:
                    continue

                # Verificar se está ocupado
                is_busy = False
                for busy in busy_slots:
                    if (slot_start < busy['end'] and slot_end > busy['start']):
                        is_busy = True
                        break

                if not is_busy:
                    available_slots.append({
                        'start': slot_start,
                        'end': slot_end,
                        'display_brt': slot_start.strftime('%d/%m %H:%M') + ' BRT',
                        'display_est': slot_start.strftime('%d/%m %I:%M %p') + ' EST',
                        'weekday': ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'][slot_start.weekday()]
                    })

    return available_slots


def format_availability_for_email(slots, max_slots=6):
    """Formatar disponibilidade para incluir no email"""
    if not slots:
        return "Não há horários disponíveis nos próximos dias."

    lines = ["Opções de horário:"]
    for i, slot in enumerate(slots[:max_slots]):
        # Converter para horário do Brasil (BRT = EST + 2h no horário normal)
        brt_hour = slot['start'].hour + 2
        lines.append(f"• **{brt_hour:02d}:00** (horário de Brasília) — {slot['start'].strftime('%I:%M %p')} EST ({slot['weekday']} {slot['start'].strftime('%d/%m')})")

    return "\n".join(lines)


def print_week_schedule():
    """Mostrar agenda da semana"""
    print("\n📅 AGENDA DA SEMANA - Daniel (Attorney)\n")
    print("=" * 60)

    events = get_events(7)

    if not events:
        print("Nenhum evento encontrado.")
        return

    current_date = None
    for event in events:
        start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
        if start:
            event_date = start[:10]
            if event_date != current_date:
                current_date = event_date
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                weekday = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'][dt.weekday()]
                print(f"\n📆 {weekday} - {dt.strftime('%d/%m/%Y')}")
                print("-" * 40)

            time_str = start[11:16] if len(start) > 10 else "All day"
            summary = event.get('summary', 'Sem título')
            print(f"  {time_str} - {summary}")

    print("\n" + "=" * 60)


def print_availability():
    """Mostrar disponibilidade do Daniel"""
    print("\n✅ DISPONIBILIDADE DO DANIEL (Attorney)\n")
    print("Regras: Quarta e Quinta, 13h-16h (Brasil) / 11AM-2PM (EST)")
    print("=" * 60)

    slots = get_daniel_availability(14)  # Próximas 2 semanas

    if not slots:
        print("\n❌ Nenhum horário disponível nas próximas 2 semanas!")
        return

    current_date = None
    for slot in slots:
        slot_date = slot['start'].strftime('%Y-%m-%d')
        if slot_date != current_date:
            current_date = slot_date
            print(f"\n📆 {slot['weekday']} - {slot['start'].strftime('%d/%m/%Y')}")

        brt_hour = slot['start'].hour + 2
        print(f"  ✅ {brt_hour:02d}:{slot['start'].strftime('%M')} BRT ({slot['start'].strftime('%I:%M %p')} EST)")

    print("\n" + "=" * 60)
    print(f"\nTotal de slots disponíveis: {len(slots)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "--setup":
        print("🔧 Configurando Google Calendar API...")
        creds = authenticate()
        if creds:
            print("✅ Autenticação concluída com sucesso!")
            print("\nPróximos passos:")
            print("  python google_calendar.py --check   # Ver disponibilidade")
            print("  python google_calendar.py --week    # Ver agenda da semana")

    elif command == "--check":
        print_availability()

    elif command == "--week":
        print_week_schedule()

    elif command == "--test":
        # Teste rápido
        service = get_calendar_service()
        if service:
            print("✅ Conexão com Google Calendar OK!")
            calendars = service.calendarList().list().execute()
            print(f"\nCalendários disponíveis:")
            for cal in calendars.get('items', []):
                print(f"  - {cal.get('summary')} ({cal.get('id')})")

    else:
        print(f"Comando desconhecido: {command}")
        print(__doc__)
