# Entrega no PASE: como o fluxo de ramos é aplicado

**Autores:** Atharv Nuthi · Felipe Vahia Malliagros

O fluxo de ramos (`feature`/`hotfix` → `develop` → `release/x.x.x` → principal) é o documento **`git-guide`** do contexto do produto, que mora no banco do PASE e se edita no painel, na tela Contexto. Esta página registra como o sistema o cumpre, e as adaptações que a prova de conceito exige.

O texto acima é da equipe e não foi alterado. Esta seção registra como o sistema o
cumpre, e as três adaptações que a PoC exige.

**Onde cada regra vive**

| Regra do guia | Onde é aplicada |
|---|---|
| matriz de integrações (§16), fluxos proibidos (§20) | `pipeline_rules.validar_integracao` |
| origem das branches (§2, §15.3–4) | `pipeline_rules.validar_origem_da_criacao`; o Executor sempre parte da principal |
| branch não incorpora a `develop` (§2, §15.5) | `git_service.incorpora_develop`, conferida antes de todo merge |
| merge direto `--no-ff`, conflito para e pede pessoa (§8, §22) | `git_service.integrar` |
| nome de branch `feature/*`, `hotfix/*`, `release/x.x.x` (§2, §16) | `conventions` - correção vira `hotfix`, o resto `feature` |
| só entra em release o aprovado nos testes (§12) | `delivery.incluir_na_release` |
| PR com o corpo exigido, só depois da validação (§7, §13) | `delivery.abrir_pr` |
| publicar exige aprovação humana por escrito (§13, §15) | `delivery.publicar` |
| falha de CI na `develop` (§8) | `delivery.rodar_ci_da_develop` desfaz a integração |
| rollback (§14) | reversão por estágio; o que está em produção só se corrige com hotfix |

**Adaptações**

1. **Sem GitHub configurado, o PASE faz o papel do Pull Request.** O texto do PR, a
   validação verde e a aprovação humana por escrito são exigidos do mesmo jeito; só o
   merge na principal é local. Com `GITHUB_TOKEN` e `GITHUB_REPO`, o PR é aberto e
   mergeado no GitHub de verdade.
2. **Falha de CI na `develop` desfaz a integração em vez de bloquear a fila.** O guia
   aceita "correção ou reversão"; reverter na hora mantém a `develop` sempre utilizável.
3. **A principal deste repositório ainda se chama `master`.** Os nomes `main` e
   `master` são tratados como a mesma branch.
