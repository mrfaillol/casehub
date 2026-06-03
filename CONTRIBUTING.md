# Contribuindo com o CaseHub

Obrigado pelo interesse em contribuir. Este guia descreve o processo e as regras.

## Antes de começar

- Leia o [`README.md`](README.md) e a [`SECURITY.md`](SECURITY.md).
- Para **vulnerabilidades de segurança**, **não** abra issue/PR público — siga a divulgação
  responsável em [`SECURITY.md`](SECURITY.md).
- Para mudanças grandes, abra uma issue de discussão antes do PR.

## Developer Certificate of Origin (DCO) — obrigatório

Todo commit deve ser assinado com `Signed-off-by` (DCO), atestando que você tem o direito de
contribuir com o código submetido:

```bash
git commit -s -m "sua mensagem"
```

PRs sem `Signed-off-by` em todos os commits não serão mesclados.

## Regras invioláveis

- **Sem segredos, sem PII.** Nenhuma contribuição pode introduzir credenciais, tokens, dados reais
  de clientes, arquivos `.env`, dumps de banco ou ambientes virtuais (`.venv`). PRs são verificados
  por varredura de segredos.
- **Sem dados pessoais em fixtures.** Use somente dados sintéticos (ex.: CPF/CNPJ válidos por dígito,
  porém fictícios).
- **Licença.** Contribuições são aceitas sob a licença do projeto ([AGPL-3.0](LICENSE)).

## Qualidade

- Siga o estilo e os padrões do código existente.
- Inclua testes quando aplicável.
- Mudanças de interface e comportamento passam por **validação visual e de desempenho** antes de
  serem consideradas concluídas.
- Mantenha PRs focados e descreva claramente o que muda e por quê.

## Fluxo

1. Fork + branch a partir de `main`.
2. Faça as mudanças com commits assinados (`-s`).
3. Garanta que a varredura de segredos e os testes passam.
4. Abra o PR descrevendo o objetivo, a mudança e como validar.
