"""
CaseHub - Document Templates Service
Generate documents from templates with placeholders
"""
import os
import re
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from jinja2 import Template, Environment
from sqlalchemy.orm import Session

from config import settings
from models import Client, Case, User


class DocumentTemplateService:
    """Service for managing and rendering document templates."""

    # Available placeholders grouped by category
    PLACEHOLDERS = {
        "client": [
            ("client.full_name", "Nome completo do cliente"),
            ("client.first_name", "Primeiro nome do cliente"),
            ("client.last_name", "Sobrenome do cliente"),
            ("client.email", "E-mail do cliente"),
            ("client.phone", "Telefone do cliente"),
            ("client.address", "Endereço do cliente"),
            ("client.date_of_birth", "Data de nascimento do cliente"),
        ],
        "case": [
            ("case.case_number", "Número do processo"),
            ("case.case_name", "Nome/assunto do processo"),
            ("case.status", "Status do processo"),
            ("case.filing_date", "Data de protocolo"),
            ("case.case_value", "Valor da causa/honorários"),
        ],
        "firm": [
            ("firm.name", "Nome do escritório"),
            ("firm.address", "Endereço do escritório"),
            ("firm.phone", "Telefone do escritório"),
            ("firm.email", "E-mail do escritório"),
            ("firm.website", "Site do escritório"),
        ],
        "dates": [
            ("today", "Data de hoje"),
            ("today_long", "Data de hoje (formato extenso)"),
            ("current_year", "Ano atual"),
        ],
    }

    # Default firm info - loaded from settings
    FIRM_INFO = {
        "name": settings.ORG_NAME,
        "address": "",
        "phone": "",
        "email": settings.ORG_EMAIL,
        "website": settings.ORG_DOMAIN,
    }

    def __init__(self, db: Session):
        self.db = db
        self.env = Environment()

    def get_context(self, client_id: Optional[int] = None, case_id: Optional[int] = None) -> Dict[str, Any]:
        """Build template context from client and case data."""
        context = {
            "firm": self.FIRM_INFO,
            "today": date.today().strftime("%d/%m/%Y"),
            "today_long": date.today().strftime("%d de %B de %Y"),
            "current_year": date.today().year,
        }

        def _client_ctx(client):
            return {
                "full_name": f"{client.first_name} {client.last_name}",
                "first_name": client.first_name,
                "last_name": client.last_name,
                "email": client.email or "",
                "phone": client.phone or "",
                "address": client.address or "",
                "date_of_birth": client.date_of_birth.strftime("%d/%m/%Y") if client.date_of_birth else "",
            }

        if client_id:
            client = self.db.query(Client).filter(Client.id == client_id).first()
            if client:
                context["client"] = _client_ctx(client)

        if case_id:
            case = self.db.query(Case).filter(Case.id == case_id).first()
            if case:
                context["case"] = {
                    "case_number": case.case_number or "",
                    "case_name": case.case_name or "",
                    "status": case.status or "",
                    "filing_date": case.filing_date.strftime("%d/%m/%Y") if case.filing_date else "",
                    "case_value": f"R$ {case.case_value:,.2f}" if case.case_value else "",
                }

                # If client not provided, get from case
                if not client_id and case.client_id:
                    client = self.db.query(Client).filter(Client.id == case.client_id).first()
                    if client:
                        context["client"] = _client_ctx(client)

        return context

    def render_template(self, template_content: str, context: Dict[str, Any]) -> str:
        """Render a template with the given context."""
        try:
            template = Template(template_content)
            return template.render(**context)
        except Exception as e:
            return f"Error rendering template: {str(e)}"

    def preview_template(self, template_content: str, client_id: Optional[int] = None, case_id: Optional[int] = None) -> str:
        """Preview a template with actual data."""
        context = self.get_context(client_id, case_id)
        return self.render_template(template_content, context)


# Default document templates
DEFAULT_TEMPLATES = [
    {
        "name": "Procuração Ad Judicia (BR)",
        "category": "contracts",
        "description": "Procuração padrão para representação legal no Brasil",
        "content": """PROCURAÇÃO AD JUDICIA ET EXTRA

OUTORGANTE: {{ client.full_name }}, brasileiro(a), portador(a) do RG e CPF/MF inscritos sob os números [COMPLETAR], residente e domiciliado(a) em {{ client.address }}, e-mail {{ client.email }}, telefone {{ client.phone }}.

OUTORGADO: {{ firm.name }}, sociedade de advogados sediada em {{ firm.address }}, e-mail {{ firm.email }}, telefone {{ firm.phone }}.

PODERES: Pelo presente instrumento de mandato, o(a) OUTORGANTE nomeia e constitui seu bastante procurador o OUTORGADO, concedendo-lhe os poderes da cláusula "ad judicia et extra" para o foro em geral, podendo propor contra quem de direito as ações competentes e defendê-lo nas contrárias, seguindo umas e outras até a decisão final.

Finalidade: Representação no processo {{ case.case_name }} ({{ case.case_number }}).

{{ firm.address }}, {{ today_long }}.


_________________________________________________
{{ client.full_name }}
"""
    },
    {
        "name": "Contrato de Honorários (BR)",
        "category": "contracts",
        "description": "Contrato padrão de honorários advocatícios",
        "content": """CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS E HONORÁRIOS

CONTRATANTE: {{ client.full_name }}, residente e domiciliado(a) em {{ client.address }}, e-mail {{ client.email }}.
CONTRATADO: {{ firm.name }}, sediada em {{ firm.address }}.

DO OBJETO: O CONTRATADO compromete-se a prestar serviços jurídicos na defesa dos interesses do(a) CONTRATANTE, especificamente no processo: {{ case.case_name }}.

DOS HONORÁRIOS: Pela prestação dos serviços, o(a) CONTRATANTE pagará ao CONTRATADO a quantia de {{ case.case_value }}, conforme as seguintes condições: [COMPLETAR FORMA DE PAGAMENTO].

DO FORO: Fica eleito o foro da comarca de {{ firm.address }} para dirimir quaisquer dúvidas oriundas deste contrato.

{{ firm.address }}, {{ today_long }}.

_________________________          _________________________
{{ client.full_name }}                    {{ firm.name }}
"""
    },
    {
        "name": "Declaração de Hipossuficiência (BR)",
        "category": "client_communication",
        "description": "Declaração de pobreza para fins de justiça gratuita",
        "content": """DECLARAÇÃO DE HIPOSSUFICIÊNCIA ECONÔMICA

Eu, {{ client.full_name }}, inscrito(a) no CPF sob o nº [COMPLETAR], residente e domiciliado(a) em {{ client.address }}, DECLARO, sob as penas da lei, que não possuo condições financeiras de arcar com as custas processuais e honorários advocatícios sem prejuízo do meu próprio sustento e da minha família.

Por ser expressão da verdade, firmo a presente declaração para que produza os seus efeitos legais.

Referência: Processo {{ case.case_number }} - {{ case.case_name }}

{{ firm.address }}, {{ today_long }}.


_________________________________________________
{{ client.full_name }}
"""
    },
    {
        "name": "Carta de Atualização do Processo",
        "category": "client_communication",
        "description": "Carta de atualização de andamento processual para o cliente",
        "content": """{{ firm.name }}
{{ firm.address }}
{{ firm.phone }} | {{ firm.email }}

{{ today_long }}

Prezado(a) {{ client.first_name }},

Gostaríamos de atualizar o status do seu caso.

INFORMAÇÕES DO PROCESSO:
Processo: {{ case.case_number }}
Assunto: {{ case.case_name }}
Status Atual: {{ case.status }}

Próximos passos e prazos:
[DETALHAR AQUI OS PRÓXIMOS PASSOS]

Qualquer dúvida, nossa equipe está à disposição.

Atenciosamente,

Equipe {{ firm.name }}
"""
    },
]


def get_template_service(db: Session) -> DocumentTemplateService:
    """Get template service instance."""
    return DocumentTemplateService(db)
