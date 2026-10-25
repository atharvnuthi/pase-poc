# Makefile do PASE PoC.
# Requer Docker Desktop (ou engine + plugin compose v2) e um shell POSIX
# (no Windows, o sh do Git Bash já serve).

COMPOSE := docker compose

.PHONY: up down logs seed reset test-core test-client lint ps metrics demos migrate migration \
        demo-d1 demo-d2 demo-d3 demo-d4 demo-d5 demo-d6 demo-d7

## up - sobe db + 4 serviços de aplicação e espera todos ficarem healthy
up:
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build --wait

## down - derruba os serviços preservando os volumes
down:
	$(COMPOSE) down

## logs - segue o log de todos os serviços
logs:
	$(COMPOSE) logs -f

## ps - estado e health de cada serviço
ps:
	$(COMPOSE) ps

## seed - popula o FinTrack e o baseline do PASE
## Cada seed chama `init_db` antes de gravar, então o schema está garantido
## mesmo que o `up --wait` tenha liberado o healthcheck antes de o esquema ser criado.
seed:
	$(COMPOSE) exec -T client-backend python -m app.seed
	$(COMPOSE) exec -T pase-core python -m app.seed

## metrics - baixa os três CSVs do capítulo de validação para ./metrics/
metrics:
	@mkdir -p metrics
	curl -s -o metrics/tasks.csv      http://localhost:8000/api/metrics/tasks.csv
	curl -s -o metrics/discards.csv   http://localhost:8000/api/metrics/discards.csv
	curl -s -o metrics/violations.csv http://localhost:8000/api/metrics/violations.csv
	@wc -l metrics/*.csv

## demos - roda os sete roteiros em sequência
demos: demo-d1 demo-d2 demo-d3 demo-d4 demo-d5 demo-d6 demo-d7

## reset - recria tudo do zero de forma idempotente
## Apaga também as branches do Executor: o banco zera e os ids das tarefas
## recomeçam do 1, então uma branch `feature/pase-1-...` antiga seria herdada pela
## tarefa #1 nova, já com código dentro.
reset:
	-$(COMPOSE) exec -T pase-core python -m app.jobs.context_backup export
	$(COMPOSE) down -v
	-git branch --list "*/pase-*" | xargs -r git branch -D
	$(MAKE) up
	$(MAKE) seed
	$(COMPOSE) exec -T pase-core python -m app.jobs.context_backup import

## reset-all - como o reset, e devolve também os documentos de contexto ao conteúdo inicial
reset-all:
	rm -f .pase-local/context-backup.json
	$(COMPOSE) down -v
	-git branch --list "*/pase-*" | xargs -r git branch -D
	$(MAKE) up
	$(MAKE) seed

## migrate - aplica as migrações pendentes no banco
migrate:
	$(COMPOSE) exec -T pase-core alembic upgrade head

## migration - cria uma migração a partir da diferença entre modelos e banco
##             uso: make migration m="descrição curta"
migration:
	@test -n "$(m)" || (echo 'uso: make migration m="descrição curta"' && exit 1)
	$(COMPOSE) exec -T pase-core alembic revision --autogenerate -m "$(m)"
	@echo "revise o arquivo gerado em pase-core/alembic/versions/ antes de commitar"

## test-core - pytest do pase-core
test-core:
	$(COMPOSE) exec -T pase-core pytest -q

## test-client - pytest do client-backend
test-client:
	$(COMPOSE) exec -T client-backend pytest -q

## lint - ruff nos dois backends (rodar antes de todo commit, ver README.md)
## Roda a partir da raiz do monorepo para que o ruff.toml do projeto valha.
lint:
	$(COMPOSE) exec -T pase-core sh -c "cd /workspace/repo && ruff check pase-core client-backend"

demo-d1:
	bash scripts/demo/d1.sh
demo-d2:
	bash scripts/demo/d2.sh
demo-d3:
	bash scripts/demo/d3.sh
demo-d4:
	bash scripts/demo/d4.sh
demo-d5:
	bash scripts/demo/d5.sh
demo-d6:
	bash scripts/demo/d6.sh
demo-d7:
	bash scripts/demo/d7.sh
