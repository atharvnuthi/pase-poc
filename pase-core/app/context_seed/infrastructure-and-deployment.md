# Infraestrutura e Implantação

## 1. Ambiente atual (local)

Tudo sobe com Docker Compose.

| Serviço | Porta | Observação |
|---|---|---|
| `client-frontend` | 3001 | Next.js em modo de desenvolvimento, com recarga automática |
| `client-backend` | 8001 | FastAPI com SQLite em volume |

Recarga automática usa leitura periódica (polling) porque o Docker Desktop no Windows não
entrega eventos de arquivo para dentro do container.

## 2. Variáveis de ambiente

| Variável | Uso |
|---|---|
| `NEXT_PUBLIC_CLIENT_API_URL` | URL pública da API do FinTrack, vista pelo navegador |
| `NEXT_PUBLIC_CORE_URL` | URL do sistema de personalização e sugestões |

Nada sensível vai em variável pública (`NEXT_PUBLIC_*`).

## 3. Como a mudança chega ao produto

1. Uma tarefa gera uma branch `feature/*` ou `hotfix/*`, nascida da principal.
2. Depois de aprovada, entra na `develop` (ambiente de testes) e roda lint, tipos, testes e build.
3. Aprovada funcionalmente, entra numa `release/x.x.x`.
4. A release é validada, abre um Pull Request e, com a aprovação humana, entra na principal.
5. A principal recebe uma tag de versão.

O detalhe está no documento `git-guide`.

## 4. Verificação de qualidade (CI)

| Alvo | Verificação |
|---|---|
| Backend | `ruff check`, `pytest` e um teste que sobe a aplicação |
| Frontend | `tsc --noEmit`, `vitest` e `next build` |

O `next build` é obrigatório porque os testes não pegam erro de componente de servidor.

## 5. Produção (ainda não existe)

Para publicar de verdade seria preciso: repositório remoto com proteção de branch, pipeline de
CI/CD externo repetindo as verificações acima, banco gerenciado no lugar do SQLite, segredos em
cofre, HTTPS, observabilidade (logs, métricas, alertas) e estratégia de rollback por tag.

## 6. Rollback

Reverter a versão (`git revert -m 1` do merge da release) ou refazer o deploy da tag anterior.
O que está em produção só se corrige por uma nova release (hotfix).
