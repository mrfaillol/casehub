import re

with open('/Users/beijaflor/Projects/casehub/templates/app/emails/list.html', 'r') as f:
    html_content = f.read()

# Replace the table structure
old_table_start = """    {% if emails %}
    <div class="el-list-card">
        <div class="el-list-table-wrap">
            <table class="el-list-table" id="emailsTable">
                <thead>
                    <tr>
                        <th scope="col" style="width:34px"><span class="visually-hidden">{% if product == "lite" %}Arquivar{% else %}Archive{% endif %}</span></th>
                        <th scope="col" style="width:32px">
                            <label for="checkAll" class="visually-hidden">{% if product == "lite" %}Selecionar todos{% else %}Select all{% endif %}</label>
                            <input type="checkbox" class="el-list-checkbox" id="checkAll" onchange="toggleAll()">
                        </th>
                        <th scope="col" style="width:22px"><span class="visually-hidden">{% if product == "lite" %}Status de leitura{% else %}Read status{% endif %}</span></th>
                        <th scope="col" style="width:18%">{% if product == "lite" %}De{% else %}From{% endif %}</th>
                        <th scope="col">{% if product == "lite" %}Assunto{% else %}Subject{% endif %}</th>
                        <th scope="col" style="width:90px">{% if product == "lite" %}Data{% else %}Date{% endif %}</th>
                        <th scope="col" style="width:160px">{% if product == "lite" %}Vinculado a{% else %}Linked To{% endif %}</th>
                        <th scope="col" style="width:46px">Notion</th>
                        <th scope="col" style="width:110px">{% if product == "lite" %}Ações{% else %}Actions{% endif %}</th>
                    </tr>
                </thead>
                <tbody id="emailsBody">"""

new_list_start = """    {% if emails %}
    <div class="el-list-card neumorphic-card">
        <div class="el-list-header-row">
            <div class="el-list-col-check">
                <label for="checkAll" class="visually-hidden">{% if product == "lite" %}Selecionar todos{% else %}Select all{% endif %}</label>
                <input type="checkbox" class="el-list-checkbox neumorphic-checkbox" id="checkAll" onchange="toggleAll()">
            </div>
            <div class="el-list-col-sender">{% if product == "lite" %}Remetente{% else %}Sender{% endif %}</div>
            <div class="el-list-col-subject">{% if product == "lite" %}Assunto{% else %}Subject{% endif %}</div>
            <div class="el-list-col-linked">{% if product == "lite" %}Vínculos{% else %}Linked To{% endif %}</div>
            <div class="el-list-col-date">{% if product == "lite" %}Data{% else %}Date{% endif %}</div>
        </div>
        <ul class="el-list-body" id="emailsBody">"""

html_content = html_content.replace(old_table_start, new_list_start)

# Replace the closing tags
html_content = html_content.replace("""                </tbody>
            </table>
        </div>
    </div>""", """        </ul>
    </div>""")

# Replace tr with li
html_content = html_content.replace("<tr class=\"el-list-row", "<li class=\"el-list-row neumorphic-row")
html_content = html_content.replace("</tr>", "</li>")

# We have to rewrite the cell contents inside the loop.
# I will use a regex to replace everything between <li class="el-list-row... > and </li>
import re

def row_replacer(match):
    li_attrs = match.group(1)
    inner = match.group(2)
    
    # We rebuild the inner HTML to match the Gmail-like layout
    # We will extract variables where possible, but we know the Jinja structure.
    
    new_inner = """
        <div class="el-list-row-drag">
            <i data-lucide="grip-vertical" aria-hidden="true"></i>
        </div>
        <div class="el-list-row-check" onclick="event.stopPropagation()">
            <label class="visually-hidden" for="check-email-{{ email.id }}">Selecionar e-mail</label>
            <input type="checkbox" class="el-list-checkbox neumorphic-checkbox email-checkbox" id="check-email-{{ email.id }}" value="{{ email.id }}" onchange="updateSelection()">
        </div>
        
        <div class="el-list-row-sender">
            {% if not email.is_read %}
            <span class="el-list-unread-dot" aria-label="{% if product == 'lite' %}Não lido{% else %}Unread{% endif %}"></span>
            {% endif %}
            <span class="sender-name">{{ email.sender[:35] }}{% if email.sender|length > 35 %}…{% endif %}</span>
        </div>
        
        <div class="el-list-row-subject">
            <span class="subject-text">{{ email.subject or '(Sem Assunto)' }}</span>
            <span class="subject-snippet">{{ email.body_text[:80] if email.body_text else '' }}</span>
        </div>
        
        <div class="el-list-row-badges" onclick="event.stopPropagation()">
            {% if dtag == "ias" %}<span class="el-list-badge el-list-badge--domain">IAS</span>{% elif dtag == "ashoori" %}<span class="el-list-badge el-list-badge--domain">Ashoori</span>{% endif %}
            {% if email.client_id %}
            <a href="{{ PREFIX }}/clients/{{ email.client_id }}" class="el-list-badge el-list-badge--client" title="{% if product == 'lite' %}Ver cliente{% else %}View client{% endif %}">
                <i data-lucide="user" aria-hidden="true"></i>
                <span>{{ email.client_first_name }} {{ email.client_last_name }}</span>
            </a>
            {% endif %}
            {% if email.case_id %}
            <a href="{{ PREFIX }}/cases/{{ email.case_id }}" class="el-list-badge el-list-badge--case" title="{% if product == 'lite' %}Ver caso{% else %}View case{% endif %}">
                <i data-lucide="folder" aria-hidden="true"></i>
                <span>#{{ email.case_number or email.case_id }}</span>
            </a>
            {% endif %}
            
            {% if email.notion_task_id and email.notion_task_id != 'NO_PARALEGAL' %}
            <i data-lucide="check-circle" class="el-list-notion el-list-notion--created" title="{% if product == 'lite' %}Task criada no Notion{% else %}Notion task created{% endif %}"></i>
            {% elif email.client_id %}
            <i data-lucide="clock" class="el-list-notion el-list-notion--pending" title="{% if product == 'lite' %}Aguardando processamento{% else %}Awaiting processing{% endif %}"></i>
            {% endif %}
        </div>
        
        <div class="el-list-row-date">
            {{ email.received_at.strftime('%d %b') if email.received_at else '—' }}
        </div>
        
        <div class="el-list-row-actions neumorphic-actions" onclick="event.stopPropagation()">
            <button type="button" class="el-list-action el-list-action--archive" onclick="archiveSingle({{ email.id }});" aria-label="Arquivar/Desarquivar">
                <i data-lucide="{% if show_archived %}undo-2{% else %}archive{% endif %}" aria-hidden="true"></i>
            </button>
            <button type="button" class="el-list-action el-list-action--reply" data-action="reply" aria-label="Responder">
                <i data-lucide="reply" aria-hidden="true"></i>
            </button>
            <button type="button" class="el-list-action el-list-action--link" data-action="link" aria-label="Vincular">
                <i data-lucide="link" aria-hidden="true"></i>
            </button>
        </div>
    """
    return f"<li class=\"el-list-row neumorphic-row{li_attrs}>{new_inner}</li>"

html_content = re.sub(r'<li class="el-list-row neumorphic-row([^>]+)>(.*?)</li>', row_replacer, html_content, flags=re.DOTALL)

with open('/Users/beijaflor/Projects/casehub/templates/app/emails/list.html', 'w') as f:
    f.write(html_content)

print("Updated list.html")
