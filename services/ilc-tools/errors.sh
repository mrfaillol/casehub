#!/bin/bash
# Gerenciador de Erros - ILC Tools

ERRORS_FILE="${APP_BASE_PATH:-/opt/casehub}/ilc-tools/data/errors.json"

case "$1" in
    list)
        echo "=== ERROS PENDENTES ==="
        cat "$ERRORS_FILE" | python3 -c "
import sys, json
errors = json.load(sys.stdin)
for i, e in enumerate(errors):
    print(f\"[{i}] {e['timestamp']} - {e['message'][:60]}\")
if not errors:
    print('Nenhum erro pendente!')
"
        ;;
    resolve)
        if [ -z "$2" ]; then
            echo "Uso: ./errors.sh resolve <numero>"
            echo "     ./errors.sh resolve all"
            exit 1
        fi
        if [ "$2" == "all" ]; then
            echo '[]' > "$ERRORS_FILE"
            echo "Todos os erros foram resolvidos!"
        else
            python3 -c "
import json
with open('$ERRORS_FILE', 'r') as f:
    errors = json.load(f)
if $2 < len(errors):
    removed = errors.pop($2)
    with open('$ERRORS_FILE', 'w') as f:
        json.dump(errors, f)
    print(f'Erro resolvido: {removed["message"][:50]}')
else:
    print('Índice inválido')
"
        fi
        ;;
    *)
        echo "Uso: ./errors.sh [list|resolve <n>|resolve all]"
        ;;
esac
