# Segurança e Conformidade

O FinTrack é uma **prova de conceito local**. Esta página diz o que está protegido, o que
não está, e o que mudaria antes de qualquer exposição real.

## 1. Modelo de ameaça atual

| Superfície | Proteção |
|---|---|
| Zona dinâmica | Payload validado no servidor e no app; widget só do catálogo; link só para rota interna; nada de HTML dinâmico |
| Entrada de formulário | Validação no servidor (422 por campo) |
| Dependências | Fixas; nova dependência exige pedido humano |
| Segredos | Só em variável de ambiente; nunca em código |
| Ambiente de execução automática | Sem rede além do provedor de LLM |

## 2. O que não existe, e por quê

- **Autenticação e autorização.** Pessoa é uma seleção, não um login. É prova de conceito
  local, nunca exposta; acrescentar auth "por precaução" daria uma falsa sensação de proteção.
- **Criptografia de dados em repouso.** O banco é um arquivo local com dados fictícios.
- **Limite de requisições e auditoria de acesso.**

## 3. Dados pessoais

Os dados de transação são **fictícios**. Antes de qualquer uso com dados reais:
- tratar valores e descrições como dados pessoais financeiros (LGPD);
- definir base legal, retenção e direito de exclusão;
- impedir que um usuário leia dados de outro (hoje é só convenção de `user_id`).

## 4. Regras para quem escreve código

- Sem `dangerouslySetInnerHTML`, `eval` ou HTML montado de string.
- Sem segredo, chave ou token no repositório.
- Sem alargar o CORS além das origens do app.
- Entrada externa sempre validada na fronteira.
- Texto livre do usuário (tickets, sugestões) é tratado como dado, nunca como instrução.

## 5. Antes de expor publicamente

Autenticação real, autorização por recurso, HTTPS, banco gerenciado com backup, limites de uso,
registro de acesso, revisão de dependências e um teste de intrusão básico.
