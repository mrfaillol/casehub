# Guia de Enriquecimento de Formulários USCIS

## Visão Geral

Este documento descreve o fluxo completo para identificar, analisar e expandir formulários USCIS no sistema CaseHub/Client-Intake.

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                      CaseHub (porta 8001)                   │
│  - Gerenciamento de casos                                   │
│  - Criação de intake packages                               │
│  - Visualização de respostas dos clientes                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Client Intake Portal (porta 8003)           │
│  - Portal público para clientes                             │
│  - Preenchimento de formulários                             │
│  - Acesso via link seguro + passphrase                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  - questionnaire_templates: definição dos formulários       │
│  - questionnaire_fields: campos de cada formulário          │
│  - questionnaire_responses: respostas dos clientes          │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura do Banco de Dados

### Tabela: questionnaire_templates

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | integer | ID único do template |
| name | varchar | Nome do formulário (ex: "Form I-485 - Application...") |
| description | text | Descrição do formulário |
| category | varchar | Categoria (USCIS, EB-2 NIW, etc.) |
| visa_types | json | Tipos de visto associados |
| is_active | boolean | Se o formulário está ativo |

### Tabela: questionnaire_fields

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | integer | ID único do campo |
| template_id | integer | FK para questionnaire_templates |
| field_name | varchar | Nome interno do campo (ex: p1_1a_family_name) |
| label | varchar | Label exibido ao usuário |
| label_pt | varchar | Label em português (opcional) |
| field_type | varchar | Tipo do campo (text, select, radio, checkbox, date, etc.) |
| is_required | boolean | Se é obrigatório |
| section | varchar | Seção do formulário |
| order | integer | Ordem de exibição |

## Fluxo de Enriquecimento

### Passo 1: Identificar o Formulário USCIS

1. Acesse o site oficial USCIS: https://www.uscis.gov/forms/all-forms
2. Encontre o formulário desejado (ex: I-485, I-130, I-864)
3. Baixe o PDF do formulário e as instruções

### Passo 2: Analisar a Estrutura do Formulário

O formulário USCIS segue uma estrutura padrão:

```
PART 1: [Nome da Parte]
  1. Campo 1
  2. Campo 2
  ...

PART 2: [Nome da Parte]
  1. Campo 1
  ...
```

### Passo 3: Mapear os Campos

Para cada campo do formulário oficial, criar uma entrada com:

```python
(
    "Section Name",           # Ex: "1A. Your Full Name"
    "field_name",             # Ex: "p1_1a_family_name" (p=part, número=item)
    "Label do Campo",         # Ex: "1.a. Family Name (Last Name)"
    "field_type",             # text, select, radio, checkbox, date, textarea, phone, email, number
    required                  # True ou False
)
```

**Convenção de nomenclatura para field_name:**
- `p1_` = Part 1
- `p2_` = Part 2
- `1a_` = Item 1.a
- `1b_` = Item 1.b
- Descrição curta: `family_name`, `given_name`, `street`, etc.

### Passo 4: Criar o Script de Atualização

Exemplo de script para expandir um formulário:

```python
#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://casehub:YOUR_DB_PASSWORD@localhost/casehub")
engine = create_engine(DATABASE_URL)

FORM_FIELDS = [
    # PART 1: INFORMATION ABOUT YOU
    ("1A. Your Full Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Your Full Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    # ... mais campos
]

def update_form(template_id: int, fields: list, form_name: str):
    with engine.connect() as conn:
        # Deletar campos existentes
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        # Inserir novos campos
        for i, field in enumerate(fields):
            section, field_name, label, field_type, required = field
            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order")
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1
            })

        conn.commit()
        print(f"{form_name} updated: {len(fields)} fields")

if __name__ == "__main__":
    update_form(TEMPLATE_ID, FORM_FIELDS, "Form Name")
```

### Passo 5: Executar no Servidor

```bash
# Copiar script para o servidor
scp expand_form.py root@31.97.174.212:/var/www/immigrant.law/casehub/

# Executar no servidor
ssh root@31.97.174.212 "cd /var/www/immigrant.law/casehub && source venv/bin/activate && python expand_form.py"
```

### Passo 6: Verificar o Resultado

```bash
ssh root@31.97.174.212 "cd /var/www/immigrant.law/casehub && source venv/bin/activate && python3 -c \"
import os
os.environ['DATABASE_URL'] = 'postgresql://casehub:YOUR_DB_PASSWORD@localhost/casehub'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT COUNT(*) as count FROM questionnaire_fields WHERE template_id = TEMPLATE_ID
    '''))
    print(f'Total campos: {result.fetchone().count}')
\""
```

## Tipos de Campo Suportados

| Tipo | Descrição | Uso |
|------|-----------|-----|
| text | Campo de texto simples | Nomes, endereços, números |
| textarea | Área de texto multilinha | Explicações, descrições |
| select | Menu dropdown | Estados, países, opções fixas |
| radio | Botões de opção | Sim/Não, escolha única |
| checkbox | Caixa de seleção | Acordos, múltiplas opções |
| date | Seletor de data | Datas de nascimento, expiração |
| phone | Campo de telefone | Números de telefone |
| email | Campo de email | Endereços de email |
| number | Campo numérico | Valores, contagens |

## IDs dos Templates Principais

| Formulário | Template ID |
|------------|-------------|
| I-130 | 38 |
| I-130A | 39 |
| I-485 | 40 |
| I-864 | 41 |
| I-765 | 42 |
| I-131 | 43 |

## Checklist para Novo Formulário

- [ ] Baixar PDF do formulário oficial USCIS
- [ ] Baixar instruções do formulário
- [ ] Identificar todas as Parts e seções
- [ ] Mapear TODOS os campos (incluindo campos opcionais)
- [ ] Criar script Python seguindo a convenção de nomenclatura
- [ ] Testar localmente se possível
- [ ] Fazer deploy no servidor
- [ ] Verificar contagem de campos
- [ ] Testar no portal do cliente

## Estrutura Padrão de Seções

A maioria dos formulários USCIS segue esta estrutura:

1. **Part 1-3**: Informações do aplicante/beneficiário
2. **Part 4-7**: Informações específicas do formulário
3. **Part 8-9**: Informações biográficas/históricas
4. **Part 10-11**: Statement do aplicante, contato, assinatura
5. **Part 12**: Informações do intérprete
6. **Part 13**: Informações do preparador
7. **Part 14**: Informações adicionais

## Arquivos de Referência

Os scripts de expansão estão em:
- `/var/www/immigrant.law/casehub/expand_i485.py`
- `/var/www/immigrant.law/casehub/expand_i130.py`
- `/var/www/immigrant.law/casehub/expand_i864.py`
- `/var/www/immigrant.law/casehub/expand_i765.py`
- `/var/www/immigrant.law/casehub/expand_i131.py`
- `/var/www/immigrant.law/casehub/expand_remaining_forms.py`

## Contato

Para questões sobre o sistema:
- Email: info@immigrant.law
