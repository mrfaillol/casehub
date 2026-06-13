import re

with open('/Users/beijaflor/Projects/casehub/templates/app/emails/list.html', 'r') as f:
    content = f.read()

# Replace the table structure with a modern list structure
old_table_start = """    {% if emails %}
    <div class="el-list-card">
        <div class="el-list-table-wrap">
            <table class="el-list-table" id="emailsTable">"""

new_list_start = """    {% if emails %}
    <div class="el-list-card neumorphic-card">
        <div class="el-list-wrap">
            <div class="el-list-header-row">
                <div class="el-list-col-check">
                    <label for="checkAll" class="visually-hidden">{% if product == "lite" %}Selecionar todos{% else %}Select all{% endif %}</label>
                    <input type="checkbox" class="el-list-checkbox neumorphic-checkbox" id="checkAll" onchange="toggleAll()">
                </div>
                <div class="el-list-col-sender">{% if product == "lite" %}De{% else %}From{% endif %}</div>
                <div class="el-list-col-subject">{% if product == "lite" %}Assunto{% else %}Subject{% endif %}</div>
                <div class="el-list-col-linked">{% if product == "lite" %}Vinculado a{% else %}Linked To{% endif %}</div>
                <div class="el-list-col-date">{% if product == "lite" %}Data{% else %}Date{% endif %}</div>
            </div>
            <ul class="el-list-body" id="emailsBody">"""

content = content.replace(old_table_start, new_list_start)

# We need to replace the table rows with li items
# Since regexing complex Jinja is hard, let's just write a script that does string manipulation
old_thead_end = """                </thead>
                <tbody id="emailsBody">"""

if old_thead_end in content:
    # remove the whole thead
    thead_start = content.find("                <thead>")
    thead_end = content.find("                <tbody id=\"emailsBody\">") + len("                <tbody id=\"emailsBody\">\n")
    if thead_start != -1:
        # already replaced the start, but we can do a better replacement
        pass

