# Política de Segurança — CaseHub

A segurança e a privacidade são pilares do CaseHub. Este documento descreve como relatar
vulnerabilidades e a postura de segurança do projeto.

## Divulgação responsável

**Não abra uma issue pública** para relatar uma vulnerabilidade. Issues públicas expõem o problema
antes que ele possa ser corrigido.

Em vez disso, use a **divulgação coordenada**:

- Use o canal privado de **[Security Advisories do GitHub](https://docs.github.com/code-security/security-advisories)**
  deste repositório ("Report a vulnerability"), ou
- Envie um e-mail para o canal de segurança indicado pelos mantenedores.

Inclua, se possível: descrição, passos de reprodução, impacto estimado e versão/commit afetado.
Comprometemo-nos a responder em prazo razoável e a creditar quem relatar, salvo pedido em contrário.

## Escopo

Em escopo: o código-fonte deste repositório.

Fora de escopo: a infraestrutura de produção, dados de clientes, e instâncias operadas por
terceiros. A configuração de produção, a topologia de implantação e os controles de defesa **não**
são documentados publicamente.

## Postura de segurança e privacidade

- **Snapshot limpo.** Este repositório público é uma fotografia do código, **sem** histórico que
  contenha segredos, **sem** dados de clientes, **sem** `.env` e **sem** PII. O ambiente de produção
  e seus dados vivem fora do repositório.
- **Multilocação por desenho.** A separação entre organizações é uma invariante validada
  continuamente; consultas são escopadas por locatário.
- **PII criptografada em repouso.** Identificadores pessoais são protegidos por criptografia.
- **LGPD.** O tratamento de dados pessoais segue a Lei nº 13.709/2018 e as diretrizes da ANPD. Os
  dados pessoais permanecem na infraestrutura do operador, nunca no código.
- **Integrações desligadas por padrão.** Conectores externos exigem ativação explícita e credenciais
  escopadas.

## Boas práticas para quem roda o CaseHub

- Nunca versione `.env`, chaves, segredos ou dados reais. Use `.env.example` como modelo.
- Rotacione credenciais regularmente e use gestores de segredo.
- Mantenha as dependências atualizadas e rode auditoria de dependências no seu pipeline.
