# Fluxo de Ramos (Git)

Guideline de fluxo e branches Git do FinTrack. É o documento normativo para pessoas,
revisores, agentes e automações de CI/CD.

## 1. Objetivo

Este guideline define o fluxo oficial de branches, integração, testes, releases e publicação dos projetos.

Ele deve ser utilizado por:

- desenvolvedores;
- revisores;
- agentes de desenvolvimento;
- automações de CI/CD;
- arquivos de harness, como `AGENTS.md` ou `CLAUDE.md`;
- Agent Skills relacionadas à criação de branches, integração, releases e validação de entregas.

O objetivo é garantir:

- rastreabilidade das alterações;
- rapidez na atualização dos ambientes de teste;
- revisão obrigatória antes da publicação;
- isolamento entre desenvolvimento, testes e produção;
- versionamento consistente;
- redução de integrações indevidas;
- fluxo previsível para humanos e agentes.

## 2. Branches oficiais

### `main`

Branch de produção.

Representa o código aprovado para publicação ou já publicado.

Regras:

- nunca realizar push direto;
- nunca combinar branches diretamente por linha de comando;
- toda alteração deve entrar por Pull Request;
- todo Pull Request deve passar pelas validações obrigatórias;
- a branch deve permanecer protegida;
- somente código proveniente de uma branch `release/x.x.x` pode ser combinado nela.

### `develop`

Branch de integração e testes.

Representa o código disponível no ambiente de testes por meio do pipeline de Continuous Delivery.

Regras:

- recebe branches `feature/*` e `hotfix/*` por merge direto;
- não exige Pull Request para integração;
- não representa uma versão pronta para produção;
- pode conter mudanças de múltiplas entregas em validação;
- não deve ser combinada direta ou indiretamente na `main`;
- não deve ser usada como origem para `feature/*`, `hotfix/*` ou `release/*`;
- falhas no pipeline bloqueiam novas integrações até correção ou reversão.

### `feature/*`

Branch de desenvolvimento de funcionalidade, melhoria técnica ou alteração planejada.

Formato:

```text
feature/<identificador-ou-descricao>
```

Exemplos:

```text
feature/JIRA-123-autenticacao-oauth
feature/adicionar-filtro-de-clientes
feature/refatorar-processamento-de-pedidos
```

Regras:

- deve ser criada sempre a partir da `main`;
- deve possuir escopo coeso e limitado;
- após o desenvolvimento, deve ser combinada diretamente na `develop` para testes;
- após aprovação nos testes, deve ser combinada diretamente na branch `release/x.x.x` correspondente;
- nunca deve ser combinada diretamente na `main`;
- não deve incorporar alterações de outras features sem justificativa;
- nunca deve incorporar a branch `develop`;
- quando precisar ser atualizada, deve receber somente alterações da `main`;
- correções encontradas nos testes devem ser realizadas na própria `feature/*` e novamente combinadas na `develop`.

Criação:

```sh
git checkout main
git pull origin main
git checkout -b feature/JIRA-123-descricao
```

### `hotfix/*`

Branch de correção urgente.

Formato:

```text
hotfix/<identificador-ou-descricao>
```

Exemplos:

```text
hotfix/JIRA-456-corrigir-timeout
hotfix/corrigir-validacao-de-token
```

Regras:

- deve ser criada sempre a partir da `main`;
- deve conter somente a correção necessária;
- deve incluir testes que comprovem a correção, sempre que aplicável;
- deve ser combinada diretamente na `develop` para validação no ambiente de testes;
- após aprovação, deve ser combinada diretamente na branch `release/x.x.x` correspondente;
- nunca deve ser combinada diretamente na `main`;
- não deve incluir refatorações ou melhorias não relacionadas ao incidente;
- nunca deve incorporar a branch `develop`;
- quando precisar ser atualizada, deve receber somente alterações da `main`;
- correções encontradas nos testes devem ser realizadas na própria `hotfix/*` e novamente combinadas na `develop`.

Criação:

```sh
git checkout main
git pull origin main
git checkout -b hotfix/JIRA-456-descricao
```

### `release/x.x.x`

Branch de preparação de publicação.

Formato:

```text
release/<major>.<minor>.<patch>
```

Exemplos:

```text
release/1.0.0
release/1.4.0
release/2.3.1
```

Regras:

- deve ser criada sempre a partir da `main`;
- deve utilizar versionamento semântico no formato `x.x.x`;
- recebe diretamente as branches `feature/*` e `hotfix/*` aprovadas para publicação;
- não exige Pull Request para receber `feature/*` e `hotfix/*`;
- deve ser usada para validação final da composição da versão;
- não deve receber desenvolvimento novo;
- deve receber somente correções necessárias para viabilizar a própria release;
- nunca deve incorporar a branch `develop`;
- após aprovação final, deve abrir Pull Request para a `main`;
- nunca deve ser combinada diretamente na `main`;
- após publicação, deve ser identificada com uma tag correspondente à versão.

Criação:

```sh
git checkout main
git pull origin main
git checkout -b release/1.4.0
git push -u origin release/1.4.0
```

## 3. Fluxo oficial

```text
main
 |
 |-- feature/* -------------|
 |                          |
 |-- hotfix/* ---------------|--> merge direto --> develop
 |                          |
 |                          v
 |                    ambiente de testes
 |
 |-- release/x.x.x <--------- merge direto das branches aprovadas
 |                          |
 |                          v
 |                    validação final
 |                          |
 |                          v
 |                    Pull Request
 |                          |
 v                          |
main <-----------------------|
 |
 v
tag x.x.x
 |
 v
publicação
```

## 4. Fluxo de uma feature

1. Atualizar a branch `main`.
2. Criar `feature/*` a partir da `main`.
3. Desenvolver somente o escopo definido.
4. Executar testes, lint e validações locais.
5. Publicar a branch no repositório remoto.
6. Combinar diretamente `feature/*` na `develop`.
7. Aguardar o pipeline de CI/CD e validar no ambiente de testes.
8. Corrigir problemas na própria `feature/*`.
9. Combinar novamente a `feature/*` na `develop`, quando necessário.
10. Obter aprovação funcional e técnica.
11. Definir a release em que a feature será publicada.
12. Combinar diretamente `feature/*` na `release/x.x.x`.
13. Validar a feature integrada com as demais mudanças da release.
14. Aguardar o Pull Request da release para a `main`.

## 5. Fluxo de um hotfix

Hotfix não elimina as etapas de revisão, teste e release.

1. Confirmar o problema e o escopo mínimo da correção.
2. Atualizar a branch `main`.
3. Criar `hotfix/*` a partir da `main`.
4. Implementar a correção.
5. Criar ou atualizar testes de regressão.
6. Executar testes, lint e validações locais.
7. Combinar diretamente `hotfix/*` na `develop`.
8. Aguardar o pipeline de CI/CD e validar a correção no ambiente de testes.
9. Corrigir problemas na própria `hotfix/*`.
10. Combinar novamente a `hotfix/*` na `develop`, quando necessário.
11. Abrir ou selecionar a branch `release/x.x.x` da publicação.
12. Combinar diretamente `hotfix/*` na `release/x.x.x`.
13. Executar validação final.
14. Publicar por meio do Pull Request da release para a `main`.

## 6. Fluxo de release

1. Definir o número da versão.
2. Atualizar a branch `main`.
3. Criar `release/x.x.x` a partir da `main`.
4. Combinar diretamente as branches `feature/*` e `hotfix/*` aprovadas para publicação.
5. Validar conflitos e dependências entre mudanças.
6. Executar testes automatizados.
7. Executar testes integrados e validações funcionais.
8. Confirmar migrations, configurações, variáveis e dependências.
9. Atualizar changelog e documentação de publicação.
10. Abrir Pull Request de `release/x.x.x` para `main`.
11. Exigir aprovação técnica e de negócio quando aplicável.
12. Combinar o Pull Request na `main`.
13. Criar a tag da versão.
14. Executar o pipeline de publicação.
15. Monitorar a publicação.
16. Executar rollback quando os critérios definidos forem violados.

Exemplo de tag:

```sh
git checkout main
git pull origin main
git tag -a 1.4.0 -m "Release 1.4.0"
git push origin 1.4.0
```

## 7. Regras obrigatórias de Pull Request

Pull Request é obrigatório somente para a integração de `release/x.x.x` na `main`.

Todo Pull Request para a `main` deve:

- possuir título claro;
- indicar origem e destino corretos;
- descrever objetivo e escopo da release;
- listar as branches e alterações incluídas;
- indicar testes executados;
- informar riscos conhecidos;
- informar impactos em banco, infraestrutura, contratos ou configurações;
- referenciar tickets, issues ou especificações quando existirem;
- possuir aprovação de pelo menos um revisor autorizado;
- passar pelas validações obrigatórias do CI;
- estar sem conflitos;
- preservar compatibilidade ou documentar explicitamente a quebra;
- possuir estratégia de rollback.

Nenhum agente ou automação pode aprovar e combinar sozinho uma alteração na `main`.

## 8. Regras de merge direto

Merge direto é permitido nos seguintes fluxos:

```text
feature/* -> develop
hotfix/*  -> develop
feature/* -> release/x.x.x
hotfix/*  -> release/x.x.x
```

Regras:

- a branch de destino deve ser atualizada antes do merge;
- testes e lint locais devem passar antes da integração;
- deve ser utilizado merge commit com `--no-ff`;
- não utilizar squash merge em integrações recorrentes;
- conflitos devem ser resolvidos na branch de destino;
- a branch de origem não deve receber `develop`;
- o responsável deve publicar imediatamente a branch de destino;
- falha no pipeline deve bloquear novas integrações;
- a alteração responsável pela falha deve ser corrigida ou revertida.

Exemplo para `develop`:

```sh
git checkout develop
git pull origin develop
git merge --no-ff feature/JIRA-123-descricao
git push origin develop
```

Exemplo para `release/*`:

```sh
git checkout release/1.4.0
git pull origin release/1.4.0
git merge --no-ff feature/JIRA-123-descricao
git push origin release/1.4.0
```

## 9. Proteções recomendadas

Configurar proteção para `main`, `develop` e `release/*`.

### `main`

- bloquear push direto;
- exigir Pull Request;
- exigir revisores;
- exigir CI aprovado;
- exigir resolução de comentários;
- bloquear force push;
- bloquear exclusão;
- restringir quem pode combinar;
- exigir branch atualizada antes do merge.

### `develop`

- permitir merge direto apenas para pessoas ou automações autorizadas;
- bloquear force push;
- bloquear exclusão;
- executar CI/CD após cada push;
- bloquear novas integrações enquanto o pipeline estiver falhando.

### `release/*`

- permitir merge direto apenas para pessoas ou automações autorizadas;
- bloquear force push;
- bloquear exclusão durante a preparação da versão;
- executar CI após cada push;
- restringir alterações após o início da validação final.

## 10. Estratégia de merge

A estratégia deve ser aplicada de forma consistente.

Padrão definido:

- `feature/*` ou `hotfix/*` para `develop`: merge direto com `--no-ff`;
- `feature/*` ou `hotfix/*` para `release/*`: merge direto com `--no-ff`;
- `release/*` para `main`: Pull Request obrigatório;
- nunca utilizar merge local diretamente na `main`;
- nunca combinar `develop` em `feature/*`, `hotfix/*`, `release/*` ou `main`.

O uso de `--no-ff` preserva a identificação da branch integrada e permite atualizações recorrentes sem reescrever a ancestralidade por squash.

## 11. Versionamento

Utilizar Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

- `MAJOR`: alteração incompatível ou mudança estrutural relevante;
- `MINOR`: nova funcionalidade compatível;
- `PATCH`: correção compatível.

Exemplos:

```text
1.0.0
1.1.0
1.1.1
2.0.0
```

A decisão da versão deve considerar o impacto conjunto de todas as alterações incluídas na release.

## 12. Critérios de entrada em uma release

Uma branch somente pode ser combinada em `release/x.x.x` quando:

- foi revisada;
- passou nos testes locais;
- passou no CI da `develop`;
- foi combinada na `develop`;
- foi testada no ambiente de testes;
- recebeu aprovação funcional quando aplicável;
- não possui bloqueios conhecidos;
- possui documentação suficiente;
- possui plano de rollback quando necessário;
- está alinhada ao escopo da versão.

## 13. Critérios de publicação

Uma release somente pode ser combinada na `main` quando:

- todas as branches previstas foram combinadas;
- testes automatizados passaram;
- testes integrados passaram;
- critérios de aceitação foram atendidos;
- migrations foram revisadas;
- configurações e secrets foram verificados;
- changelog foi atualizado;
- riscos foram registrados;
- observabilidade da mudança está disponível;
- rollback foi definido;
- aprovação humana foi registrada.

## 14. Rollback

Toda release deve possuir uma estratégia de rollback compatível com a mudança.

A estratégia pode incluir:

- reversão da versão;
- redeploy da tag anterior;
- desativação por feature flag;
- rollback de migration compatível;
- correção por nova release de patch.

Não executar rollback destrutivo de banco sem procedimento validado e aprovação humana.

## 15. Regras para agentes e automações

Ao utilizar este guideline como harness ou Agent Skill, o agente deve:

1. identificar a branch atual;
2. identificar o tipo de mudança;
3. confirmar a origem obrigatória da branch;
4. impedir criação de `feature/*`, `hotfix/*` ou `release/*` a partir da `develop`;
5. impedir que `feature/*`, `hotfix/*` ou `release/*` incorporem a `develop`;
6. permitir merge direto somente nos fluxos definidos neste documento;
7. impedir push ou merge direto na `main`;
8. exigir Pull Request para toda integração na `main`;
9. verificar se a branch foi testada na `develop`;
10. verificar se existe uma `release/x.x.x` válida;
11. impedir publicação de branches individuais;
12. solicitar aprovação humana antes de combinar uma release na `main`;
13. executar verificações antes e depois de cada ação;
14. interromper o fluxo quando encontrar conflito, falha de teste ou destino incorreto.

### Ações permitidas sem aprovação adicional

- consultar branches;
- verificar diferenças;
- executar testes;
- executar lint;
- preparar commits;
- criar branch seguindo a convenção;
- combinar `feature/*` ou `hotfix/*` na `develop`;
- combinar `feature/*` ou `hotfix/*` em `release/x.x.x`;
- preparar descrição de Pull Request;
- verificar status do CI.

Essas ações somente são permitidas quando:

- o agente possui autorização explícita no repositório;
- o destino está correto;
- testes locais passaram;
- não existem conflitos não triviais;
- nenhuma proteção precisa ser ignorada.

### Ações que exigem aprovação humana

- combinar Pull Request na `main`;
- criar tag de produção;
- iniciar publicação em produção;
- executar rollback;
- alterar proteção de branches;
- ignorar validações;
- executar force push;
- excluir branch protegida;
- resolver conflito com impacto funcional não trivial;
- incluir em uma release uma branch ainda não aprovada em testes.

## 16. Validações automáticas sugeridas

O CI deve verificar, quando aplicável:

- padrão do nome da branch;
- origem permitida da branch;
- destino permitido da integração;
- testes unitários;
- testes de integração;
- lint;
- análise estática;
- cobertura mínima;
- segurança de dependências;
- presença de changelog em release;
- versão válida;
- ausência de secrets;
- migrations reversíveis ou documentadas;
- contratos e schemas;
- artefatos de build.

Matriz mínima de integrações:

| Origem | Destino | Método |
| :---- | :---- | :---- |
| `feature/*` | `develop` | merge direto com `--no-ff` |
| `hotfix/*` | `develop` | merge direto com `--no-ff` |
| `feature/*` | `release/x.x.x` | merge direto com `--no-ff` |
| `hotfix/*` | `release/x.x.x` | merge direto com `--no-ff` |
| `release/x.x.x` | `main` | Pull Request obrigatório |
| `develop` | `main` | proibido |
| qualquer branch | `main` por push direto | proibido |

## 17. Convenção de commits

Formato recomendado:

```text
<tipo>(<escopo>): <descrição>
```

Exemplos:

```text
feat(auth): adicionar login com OAuth
fix(api): corrigir timeout na consulta
test(order): adicionar teste de regressão
docs(release): atualizar changelog da versão 1.4.0
refactor(payment): separar validação de cobrança
```

Tipos comuns:

- `feat`;
- `fix`;
- `refactor`;
- `test`;
- `docs`;
- `chore`;
- `build`;
- `ci`;
- `perf`;
- `revert`.

## 18. Checklist do desenvolvedor

### Antes de combinar em `develop`

- A branch foi criada a partir da `main`.
- O nome da branch segue a convenção.
- O escopo está limitado à demanda.
- A branch não incorporou a `develop`.
- Os testes locais passaram.
- O lint passou.
- Não existem secrets ou arquivos indevidos.
- A documentação necessária foi atualizada.
- A branch `develop` está com o pipeline aprovado.

### Antes de combinar em `release/x.x.x`

- O destino da integração está correto.
- A mudança foi combinada na `develop`.
- A mudança foi validada no ambiente de testes.
- A aprovação funcional foi registrada.
- A revisão técnica foi concluída.
- A release correta foi identificada.
- Dependências com outras branches foram verificadas.
- O plano de rollback foi definido quando necessário.
- A branch de origem não incorporou a `develop`.

## 19. Checklist do revisor

- O objetivo da alteração está claro.
- A origem e o destino estão corretos.
- A alteração respeita o escopo.
- A implementação está compreensível.
- Os testes cobrem os principais riscos.
- Não existem mudanças não relacionadas.
- Segurança e permissões foram avaliadas.
- Contratos e compatibilidade foram avaliados.
- Observabilidade foi considerada.
- A estratégia de rollback é adequada.
- O CI está aprovado.

## 20. Fluxos proibidos

Os fluxos abaixo são proibidos:

- `feature/* -> main`;
- `hotfix/* -> main`;
- `develop -> main`;
- push direto para `main`;
- `feature/*` criada a partir de `develop`;
- `hotfix/*` criada a partir de `develop`;
- `release/*` criada a partir de `develop`;
- `develop -> feature/*`;
- `develop -> hotfix/*`;
- `develop -> release/*`;
- squash merge recorrente em `develop`;
- squash merge recorrente em `release/*`;
- publicação sem `release/x.x.x`;
- publicação sem Pull Request para `main`;
- merge com CI falhando sem correção ou reversão;
- bypass de aprovação sem autorização formal.

## 21. Exemplo completo

```sh
# Criar a feature a partir da main
git checkout main
git pull origin main
git checkout -b feature/JIRA-123-nova-funcionalidade


# Desenvolver, testar e publicar
git add .
git commit -m "feat(modulo): adicionar nova funcionalidade"
git push -u origin feature/JIRA-123-nova-funcionalidade


# Integrar diretamente na develop para testes
git checkout develop
git pull origin develop
git merge --no-ff feature/JIRA-123-nova-funcionalidade
git push origin develop


# Validar no ambiente de testes
# Correções devem ser feitas na própria feature e integradas novamente


# Criar a release a partir da main
git checkout main
git pull origin main
git checkout -b release/1.5.0
git push -u origin release/1.5.0


# Integrar diretamente a feature aprovada na release
git checkout release/1.5.0
git pull origin release/1.5.0
git merge --no-ff feature/JIRA-123-nova-funcionalidade
git push origin release/1.5.0


# Executar validação final


# Abrir PR: release/1.5.0 -> main


# Após aprovação e merge:
git checkout main
git pull origin main
git tag -a 1.5.0 -m "Release 1.5.0"
git push origin 1.5.0
```

## 22. Critério de parada para agentes

O agente deve parar e solicitar intervenção humana quando:

- a branch de origem estiver incorreta;
- o destino da integração violar este guideline;
- a branch de origem tiver incorporado a `develop`;
- existirem conflitos não triviais;
- testes obrigatórios falharem;
- o CI estiver incompleto ou reprovado;
- a versão da release for ambígua;
- houver mudança destrutiva;
- houver alteração de contrato público;
- o rollback não estiver definido para uma mudança crítica;
- a ação envolver merge na `main`, tag ou publicação;
- houver necessidade de ignorar qualquer proteção.

## 23. Resumo normativo

1. `feature/*` sempre nasce da `main`.
2. `hotfix/*` sempre nasce da `main`.
3. `release/x.x.x` sempre nasce da `main`.
4. `feature/*` e `hotfix/*` entram diretamente na `develop` com merge `--no-ff`.
5. `develop` alimenta o ambiente de testes por CD.
6. `feature/*` e `hotfix/*` aprovadas entram diretamente em `release/x.x.x` com merge `--no-ff`.
7. Nenhuma branch de origem pode incorporar a `develop`.
8. Somente `release/x.x.x` pode entrar na `main`.
9. Toda entrada na `main` ocorre por Pull Request.
10. Toda publicação utiliza uma branch `release/x.x.x`.
11. Falhas no pipeline bloqueiam novas integrações até correção ou reversão.
12. A publicação exige aprovação humana, CI aprovado e estratégia de rollback.
