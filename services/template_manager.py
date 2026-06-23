"""
Template Manager for Lead Follow-ups
Provides WhatsApp and Email templates with variable substitution
"""

from typing import Dict, List, Any, Optional
import os
import re

# Organization name for templates - loaded from env or config
_ORG_NAME = os.environ.get("ORG_NAME", "CaseHub")
_ORG_DOMAIN = os.environ.get("ORG_DOMAIN", "")

# =============================================================================
# WHATSAPP TEMPLATES (Quick Messages)
# =============================================================================

WHATSAPP_TEMPLATES = {
    "greeting_pt": {
        "name": "Saudação Inicial",
        "language": "pt",
        "channel": "whatsapp",
        "content": """Olá {name}!

Ficamos felizes em ajudar.

Somos especializados em vistos e imigração para os Estados Unidos, oferecendo orientação clara e objetiva.

Oferecemos uma ligação inicial gratuita com nossa equipe. Gostaria de agendar?
{freecall_url}

Para análise específica do caso, o próximo passo é uma consulta com um de nossos advogados ($99):
{meeting_url}

Atenciosamente,
{org_name}"""
    },
    "greeting_en": {
        "name": "Initial Greeting",
        "language": "en",
        "channel": "whatsapp",
        "content": """Hello {name}!

We are glad to help.

We specialize in U.S. visas and immigration, providing clear and straightforward guidance.

We offer a free intro call with our team. Would you like to schedule it?
{freecall_url}

For specific case analysis, the next step is a consultation with our attorneys ($99):
{meeting_url}

Warm Regards,
{org_name}"""
    },
    "followup_1_pt": {
        "name": "Follow-up 1 (4 dias)",
        "language": "pt",
        "channel": "whatsapp",
        "content": """Olá {name}!

Não tivemos retorno seu.

Gostaria de agendar uma reunião inicial gratuita? Ou talvez uma consulta com nossos advogados?

Estamos aqui para ajudar!

Atenciosamente,
{org_name}"""
    },
    "followup_1_en": {
        "name": "Follow-up 1 (4 days)",
        "language": "en",
        "channel": "whatsapp",
        "content": """Hello {name}!

We haven't heard from you.

Would you like to schedule a free intro meeting? Or maybe a consultation with our attorneys?

We are here to help!

Warm Regards,
{org_name}"""
    },
    "followup_2_pt": {
        "name": "Follow-up Final (7 dias)",
        "language": "pt",
        "channel": "whatsapp",
        "content": """Olá {name}.

Como não tivemos retorno, vamos arquivar seu contato para necessidades futuras.

Se desejar agendar uma reunião inicial gratuita, é só nos avisar. Estamos aqui para ajudar.

Muito obrigado!
{org_name}"""
    },
    "followup_2_en": {
        "name": "Final Follow-up (7 days)",
        "language": "en",
        "channel": "whatsapp",
        "content": """Hello {name}.

We haven't heard from you, so we will archive your contact for future needs.

If you would like to schedule a free initial meeting, just let us know. We are here to help.

Thank you very much!
{org_name}"""
    },
    "consultation_confirm_pt": {
        "name": "Confirmação de Consulta",
        "language": "pt",
        "channel": "whatsapp",
        "content": """Prezado(a) {name},

Sua reunião com o advogado está confirmada para {date} às {time}.

Link para a reunião: {meet_link}

Por favor, preencha o formulário de intake antes da consulta:
https://docs.google.com/forms/d/19DozIZBJTpT_u3ahrWQpgllNlWdhFdQ6gdnDIxLxgh8/viewform

Caso surja qualquer dúvida, não hesite em nos contatar.

Atenciosamente,
{org_name}"""
    },
    "consultation_confirm_en": {
        "name": "Consultation Confirmation",
        "language": "en",
        "channel": "whatsapp",
        "content": """Dear {name},

Your meeting with Attorney has been confirmed for {date} at {time}.

Meeting link: {meet_link}

Please complete the intake form before your consultation:
https://docs.google.com/forms/d/19DozIZBJTpT_u3ahrWQpgllNlWdhFdQ6gdnDIxLxgh8/viewform

Please don't hesitate to let us know if you have any questions.

Warm Regards,
{org_name}"""
    },
    "payment_confirm_en": {
        "name": "Payment Confirmation",
        "language": "en",
        "channel": "whatsapp",
        "content": """Dear {name},

We are pleased to confirm that we have received your payment.

Thank you very much for your prompt attention and cooperation.

Please don't hesitate to let us know if you have any questions.

Warm Regards,
{org_name}"""
    },
    "forwarding_en": {
        "name": "Forwarded to Legal Team",
        "language": "en",
        "channel": "whatsapp",
        "content": """Hello {name}!

Your message has been sent to our legal team for review. We will get back to you with an update as soon as possible.

Please don't hesitate to let us know if you have any questions.

Warm regards,
{org_name}"""
    },
}

# =============================================================================
# EMAIL TEMPLATES
# =============================================================================

EMAIL_TEMPLATES = {
    "fee_info_en": {
        "name": "Fee Information",
        "language": "en",
        "channel": "email",
        "subject": "Payment Options - {visa_type} Visa",
        "content": """Dear {name},

We would like to share the payment options available for your {visa_type} process. Please find the details below:

Attorney Fees: USD ${fee_amount}

Payment Methods:
• Bank Transfer - You may complete the payment via U.S. or international bank transfer. Bank details will be provided once you confirm this option.
• Credit or Debit Card (via Stripe link) - You can make a secure payment through a Stripe link that we will send to you upon request.

Payment Plans and Discounts:
• 10% OFF – Full Payment Upfront
• 5% OFF – Split Payment (50/50)
• Regular Plan – Monthly Installments (half upfront, rest in 5 monthly payments)

Please let us know which payment option and plan you prefer so we can provide the appropriate instructions and links.

Warm regards,
{org_name}"""
    },
    "onboarding_en": {
        "name": "Client Onboarding",
        "language": "en",
        "channel": "email",
        "subject": f"Welcome to {_ORG_NAME} - Getting Started",
        "content": """Hello {name}!

Thank you for choosing our firm to assist with your immigration matter. Nice to meet you. My name is {attorney_name}, and I am the attorney who will manage your case.

Quick introduction: I am an Immigration Lawyer with years of experience, licensed in the US, and I have a master's degree in Immigration Law as well. I'll make sure to complete your case in the best and quickest way possible.

To get started, let's schedule an onboarding call to discuss your case in more detail. Please let me know a few times that you're available for a call.

Here are your credentials to log into your e-immigration account:
[CLIENT_PORTAL_URL]

Username: {email}
Password: [Will be provided separately]

You can use this link to upload all documents as you gather them. In your e-immigration account you will also find the signed retainer agreement for your records, the list of documents we need from you, and two documents you must complete: expansion questionnaire and testimonial letter questionnaire.

Please don't hesitate to contact us via SMS, email or WhatsApp. All questions are important.

Warm Regards,
{org_name}"""
    },
    "meeting_proposal_en": {
        "name": "Meeting Proposal",
        "language": "en",
        "channel": "email",
        "subject": f"Scheduling Your Consultation - {_ORG_NAME}",
        "content": """Hello {name}!

Thank you for choosing our firm for your consultation. We have availability on {date} at {time}.

Please let me know a 30-minute slot that works for you. If these times aren't convenient, feel free to share two or three alternatives.

Once confirmed, I'll send a calendar invite with the details.

Warm regards,
{org_name}"""
    },
    "meeting_confirm_en": {
        "name": "Meeting Confirmation",
        "language": "en",
        "channel": "email",
        "subject": "Meeting Confirmed - {date}",
        "content": """Dear {name},

Your meeting with Attorney has been confirmed for {date} at {time}.

Meeting Details:
• Date: {date}
• Time: {time}
• Duration: 30 minutes
• Link: {meet_link}

Important Information Before Your Consultation:

1. Cancellation and Rescheduling Policy
Please note that any cancellations or rescheduling requests must be made at least 2 business days in advance.

2. Intake Form (Required)
Please complete the intake form: https://docs.google.com/forms/d/19DozIZBJTpT_u3ahrWQpgllNlWdhFdQ6gdnDIxLxgh8/viewform

3. Documents and Questions
Please send us any relevant documents related to your case, as well as any questions you may have in advance.

A calendar invite will be sent to you shortly.

Respectfully,
{org_name}"""
    },
}

# =============================================================================
# TEMPLATE FUNCTIONS
# =============================================================================

def get_all_templates() -> List[Dict[str, Any]]:
    """Get all available templates."""
    templates = []
    
    for tid, tpl in WHATSAPP_TEMPLATES.items():
        templates.append({
            "id": tid,
            "name": tpl["name"],
            "language": tpl["language"],
            "channel": tpl["channel"],
            "preview": tpl["content"][:100] + "..." if len(tpl["content"]) > 100 else tpl["content"],
        })
    
    for tid, tpl in EMAIL_TEMPLATES.items():
        templates.append({
            "id": tid,
            "name": tpl["name"],
            "language": tpl["language"],
            "channel": tpl["channel"],
            "subject": tpl.get("subject", ""),
            "preview": tpl["content"][:100] + "..." if len(tpl["content"]) > 100 else tpl["content"],
        })
    
    return templates


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific template by ID."""
    if template_id in WHATSAPP_TEMPLATES:
        return {"id": template_id, **WHATSAPP_TEMPLATES[template_id]}
    if template_id in EMAIL_TEMPLATES:
        return {"id": template_id, **EMAIL_TEMPLATES[template_id]}
    return None


def substitute_variables(content: str, variables: Dict[str, str]) -> str:
    """Replace {variable} placeholders with actual values."""
    result = content
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value) if value else "")
    return result


def preview_template(template_id: str, lead: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a preview of the template with lead data substituted."""
    template = get_template(template_id)
    if not template:
        return {"error": "Template not found"}
    
    # Build variables from lead data
    variables = {
        "name": lead.get("name") or lead.get("display_name") or lead.get("whatsapp_name") or "Client",
        "email": lead.get("email") or "",
        "phone": lead.get("phone") or "",
        "visa_type": lead.get("visa_interest") or "EB-2 NIW",
        "fee_amount": "8,000",
        "date": "[DATE]",
        "time": "[TIME]",
        "meet_link": "meet.google.com/xxx-xxxx-xxx",
    }
    
    content = substitute_variables(template["content"], variables)
    subject = substitute_variables(template.get("subject", ""), variables) if template.get("subject") else None
    
    return {
        "id": template_id,
        "name": template["name"],
        "channel": template["channel"],
        "language": template["language"],
        "subject": subject,
        "content": content,
        "recipient": {
            "name": variables["name"],
            "phone": variables["phone"],
            "email": variables["email"],
        },
    }


def get_templates_by_channel(channel: str) -> List[Dict[str, Any]]:
    """Get templates filtered by channel (whatsapp or email)."""
    templates = get_all_templates()
    return [t for t in templates if t["channel"] == channel]


def get_templates_by_language(language: str) -> List[Dict[str, Any]]:
    """Get templates filtered by language."""
    templates = get_all_templates()
    return [t for t in templates if t["language"] == language]
