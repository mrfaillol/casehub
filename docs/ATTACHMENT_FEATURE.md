# Documentacao: Visualizacao de Anexos de Email

**Data:** 2026-02-04
**Autor:** Claude Code

---

## Resumo

Implementacao de sistema para visualizar e baixar anexos de emails diretamente na interface do CaseHub.

---

## Arquivos Modificados

### 1. routes/emails.py

**Backup:** `emails.py.backup.20260204_*`

**Rotas adicionadas:**

```
GET /emails/attachments/{attachment_id}/download  - Download do anexo
GET /emails/attachments/{attachment_id}/preview   - Preview inline (PDF/imagens)
```

**Seguranca:**
- Validacao de path traversal
- Verificacao de existencia do arquivo
- Erros 404/403 apropriados

### 2. templates/emails/view.html

**Backup:** `view.html.backup.20260204_*`

**Mudancas:**
- Icones por tipo de arquivo (PDF, imagem, Word, Excel)
- Botao Preview (olho) - abre em nova aba
- Botao Download (seta) - forca download

---

## Banco de Dados

**Tabela:** email_attachments

| Coluna | Tipo | Descricao |
|--------|------|-----------|
| id | SERIAL | PK |
| message_id | INTEGER | FK para email_messages |
| filename | VARCHAR(300) | Nome original |
| mime_type | VARCHAR(100) | Tipo MIME |
| file_size | INTEGER | Tamanho em bytes |
| file_path | VARCHAR(500) | Caminho no disco |
| created_at | TIMESTAMP | Data de criacao |

**Arquivos:** /var/www/legacy.example/casehub/uploads/email_attachments/

---

## Icones por Tipo

| Extensao | Icone | Cor |
|----------|-------|-----|
| .pdf | fa-file-pdf | Vermelho |
| .jpg/.png/.gif | fa-file-image | Azul claro |
| .doc/.docx | fa-file-word | Azul |
| .xls/.xlsx | fa-file-excel | Verde |
| Outros | fa-file | Cinza |

---

## Como Testar

1. Acesse https://legacy.example/casehub/emails
2. Abra um email com anexos
3. Use os botoes Preview/Download na secao Attachments

---

## Rollback

```bash
# Restaurar backups
cp /var/www/legacy.example/casehub/routes/emails.py.backup.20260204_* \
   /var/www/legacy.example/casehub/routes/emails.py

cp /var/www/legacy.example/casehub/templates/emails/view.html.backup.20260204_* \
   /var/www/legacy.example/casehub/templates/emails/view.html

# Reiniciar
pm2 restart casehub
```

---

## Nao Conflita Com

- Cores de paralegal (vermelho/amarelo)
- Indicadores Notion
- Legenda visual
