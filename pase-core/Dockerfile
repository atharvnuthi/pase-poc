# SPEC-01 §3: python:3.12-slim + git. Instala as dependências do pase-core E do
# client-backend, porque o Executor roda ruff/pytest do alvo dentro deste ambiente.
#
# O contexto de build é a RAIZ do monorepo (ver docker-compose.yml), justamente
# para conseguir enxergar client-backend/requirements.txt.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# git para o isolamento do Executor; Node porque ele também verifica o
# client-frontend (tsc, vitest e next build) - mesma simetria do ruff/pytest no
# client-backend.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Identidade dos commits feitos pelo Executor (SPEC-04 §6.7)
RUN git config --global user.name "PASE Bot" \
    && git config --global user.email "pase-bot@pase.local" \
    && git config --global init.defaultBranch main \
    && git config --global --add safe.directory '*'

WORKDIR /app

COPY pase-core/requirements.txt /tmp/requirements-core.txt
COPY client-backend/requirements.txt /tmp/requirements-client.txt
RUN pip install -r /tmp/requirements-core.txt -r /tmp/requirements-client.txt

# Dependências do client-frontend na imagem. O Executor liga este node_modules
# ao clone de trabalho em vez de instalar a cada run - instalar no clone somaria
# ~40s e uma dependência de rede a cada execução.
ENV FRONTEND_NODE_MODULES=/opt/frontend/node_modules
COPY client-frontend/package.json /opt/frontend/package.json
RUN cd /opt/frontend && npm install --no-audit --no-fund

COPY pase-core/ /app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
