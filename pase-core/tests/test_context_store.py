"""Documentos de contexto no banco: semente, versões, leitura por etapa e API."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common import context_store, prompts
from app.common.models import ContextDocument
from tests.conftest import requires_db


@pytest.fixture
def limpo(session):
    def zerar():
        session.execute(text("DELETE FROM context_document_versions"))
        session.execute(text("DELETE FROM context_documents"))
        session.commit()

    zerar()
    yield session
    zerar()


@pytest.fixture
def client(limpo):
    from app.main import app

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# A semente em si (não precisa de banco)
# --------------------------------------------------------------------------- #


def test_toda_referencia_do_mapa_de_leituras_existe_na_semente():
    """Um slug errado no mapa deixaria uma etapa sem um documento, em silêncio."""
    semente = set(context_store._da_semente())
    for chave, leitura in context_store.LEITURAS.items():
        for ref in leitura["documentos"]:
            if ref.endswith("/*"):
                assert any(s.startswith(ref[:-1]) for s in semente), (chave, ref)
            else:
                assert ref in semente, (chave, ref)


def test_todo_documento_da_semente_tem_nome_valido_e_titulo():
    for slug, texto in context_store._da_semente().items():
        assert context_store.SLUG.match(slug), slug
        assert texto.lstrip().startswith("# "), f"{slug} sem título"


def test_a_semente_cobre_o_conjunto_pedido():
    semente = set(context_store._da_semente())
    esperado = {
        "project-context", "scope-and-constraints", "requirements", "features",
        "architecture-and-design", "architecture-principles", "database", "ui-ux",
        "engineering-guidelines", "design-patterns-and-standards", "security-and-compliance",
        "infrastructure-and-deployment", "git-guide",
    }
    assert esperado <= semente
    assert any(s.startswith("adrs/") for s in semente)
    assert any(s.startswith("design-systems/") for s in semente)


def test_a_semente_nao_usa_travessao_longo():
    for slug, texto in context_store._da_semente().items():
        assert "—" not in texto, slug


# --------------------------------------------------------------------------- #
# Banco
# --------------------------------------------------------------------------- #


@requires_db
def test_bootstrap_insere_tudo_e_nao_sobrescreve_edicoes(limpo):
    inseridos = context_store.bootstrap(limpo)
    assert inseridos == len(context_store._da_semente())

    context_store.salvar(limpo, "scope-and-constraints", "# Escopo\n\neditado", note="teste")
    assert context_store.bootstrap(limpo) == 0  # nada novo
    assert context_store.obter(limpo, "scope-and-constraints").content.endswith("editado")


@requires_db
def test_salvar_cria_versao_e_igual_nao_cria(limpo):
    context_store.bootstrap(limpo)

    doc, mudou = context_store.salvar(limpo, "features", "# Features\n\nnovo", note="nota")
    assert mudou and doc.version == 2 and doc.updated_by == "humano"

    _, mudou = context_store.salvar(limpo, "features", "# Features\n\nnovo", note="igual")
    assert not mudou
    assert [v.version for v in context_store.historico(limpo, "features")] == [2, 1]


@requires_db
def test_titulo_acompanha_o_primeiro_cabecalho(limpo):
    context_store.bootstrap(limpo)
    doc, _ = context_store.salvar(limpo, "features", "# Outro nome\n\ncorpo", note="n")
    assert doc.title == "Outro nome"


@requires_db
def test_restaurar_volta_o_texto_como_versao_nova(limpo):
    context_store.bootstrap(limpo)
    original = context_store.obter(limpo, "requirements").content
    context_store.salvar(limpo, "requirements", "# Req\n\nmudou", note="mudança")

    doc, mudou = context_store.restaurar(limpo, "requirements", 1)

    assert mudou and doc.content == original and doc.version == 3  # o histórico só cresce
    with pytest.raises(context_store.ContextoError):
        context_store.restaurar(limpo, "requirements", 99)


@requires_db
@pytest.mark.parametrize("slug", ["Maiusculo", "a/b/c", "com espaco", "../fuga", ""])
def test_nome_invalido_e_recusado(limpo, slug):
    with pytest.raises(context_store.ContextoError):
        context_store.criar(limpo, slug, "# x\n\ny")


@requires_db
def test_documento_vazio_e_duplicado_sao_recusados(limpo):
    context_store.bootstrap(limpo)
    with pytest.raises(context_store.ContextoError, match="vazio"):
        context_store.salvar(limpo, "features", "   ", note="n")
    with pytest.raises(context_store.ContextoError, match="já existe"):
        context_store.criar(limpo, "features", "# x\n\ny")


# --------------------------------------------------------------------------- #
# Cada etapa lê só o que precisa
# --------------------------------------------------------------------------- #


@requires_db
def test_cada_etapa_recebe_so_os_documentos_dela(limpo):
    context_store.bootstrap(limpo)

    funil = context_store.compor(limpo, "funil")
    execucao = context_store.compor(limpo, "execucao")
    planejamento = context_store.compor(limpo, "planejamento")
    revisao = context_store.compor(limpo, "revisao")

    assert "Contexto Geral do Projeto" in funil and "Guia de Engenharia" not in funil
    assert "Guia de Engenharia" in execucao and "Contexto Geral do Projeto" not in execucao
    assert "FinTrack Ledger" in execucao  # pasta inteira entra por curinga
    assert "ADR-0001" in planejamento and "ADR-0001" not in execucao
    assert "Requisitos do FinTrack" in revisao
    # o guia de git não entra em nenhum prompt hoje: é para pessoas e agentes futuros
    for texto in (funil, execucao, planejamento, revisao):
        assert "Fluxo de Ramos" not in texto


@requires_db
def test_editar_o_documento_vale_na_proxima_leitura(limpo):
    """Tempo real: sem commit, sem reiniciar. É o que o painel promete."""
    context_store.bootstrap(limpo)
    limpo.commit()

    antes = prompts.load_project_context()
    assert "Metas de economia" in antes

    context_store.salvar(
        limpo,
        "project-context",
        "# Contexto\n\nO produto agora também faz metas de economia.",
        note="mudança de escopo",
    )
    limpo.commit()

    depois = prompts.load_project_context()
    assert "agora também faz metas" in depois


@requires_db
def test_etapa_sem_o_documento_obrigatorio_levanta(limpo):
    context_store.bootstrap(limpo)
    doc = context_store.obter(limpo, "project-context")
    limpo.execute(
        text("DELETE FROM context_document_versions WHERE document_id = :i"), {"i": doc.id}
    )
    limpo.delete(doc)
    limpo.flush()
    with pytest.raises(context_store.ContextoError, match="obrigatório"):
        context_store.compor(limpo, "funil")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@requires_db
def test_api_lista_documentos_e_o_mapa_de_leituras(client):
    corpo = client.get("/api/context").json()

    slugs = {d["slug"] for d in corpo["documentos"]}
    assert {"project-context", "git-guide"} <= slugs
    funil = next(x for x in corpo["leituras"] if x["key"] == "funil")
    assert "P2a" in funil["prompts"] and "project-context" in funil["documentos"]


@requires_db
def test_api_edita_documento_com_pasta_no_nome_e_guarda_historico(client):
    slug = "adrs/0001-dinheiro-em-decimal"

    r = client.put(
        f"/api/context/doc/{slug}",
        json={"content": "# ADR-0001\n\nrevisada", "note": "revisão"},
    )
    assert r.status_code == 200 and r.json()["salvo"] and r.json()["version"] == 2
    assert "revisada" in r.json()["diff"]

    historico = client.get(f"/api/context/doc/{slug}/history").json()
    assert [h["version"] for h in historico] == [2, 1]
    assert historico[0]["note"] == "revisão"

    doc = client.get(f"/api/context/doc/{slug}").json()
    assert doc["content"].endswith("revisada")
    assert any(x["key"] == "planejamento" for x in doc["readers"])


@requires_db
def test_api_restaura_e_exige_nota_para_editar(client):
    slug = "features"
    original = client.get(f"/api/context/doc/{slug}").json()["content"]
    client.put(f"/api/context/doc/{slug}", json={"content": "# F\n\nx", "note": "n"})

    assert client.put(f"/api/context/doc/{slug}", json={"content": "# F\n\ny"}).status_code == 422

    r = client.post(f"/api/context/doc/{slug}/restore", json={"version": 1})
    assert r.status_code == 200
    assert client.get(f"/api/context/doc/{slug}").json()["content"] == original


@requires_db
def test_api_cria_documento_novo_e_recusa_nome_ruim(client):
    r = client.post(
        "/api/context",
        json={"slug": "adrs/0006-teste", "content": "# ADR-0006: Teste\n\ncorpo"},
    )
    assert r.status_code == 201 and r.json()["folder"] == "adrs"

    assert client.post("/api/context", json={"slug": "Ruim Nome", "content": "# x"}).status_code == 422
    assert client.get("/api/context/doc/nao-existe").status_code == 404


@requires_db
def test_api_proposta_da_ia_nao_grava(client, mock_providers):
    mock_providers.responses = [
        json.dumps(
            {
                "aplicavel": True,
                "reasoning": "ok",
                "summary": "acrescenta uma regra",
                "content": "# Features\n\nversão proposta",
            }
        )
    ]
    antes = client.get("/api/context/doc/features").json()

    r = client.post("/api/context/doc/features/propose", json={"request": "mude algo"})

    assert r.json()["aplicavel"] and "versão proposta" in r.json()["diff"]
    depois = client.get("/api/context/doc/features").json()
    assert depois["version"] == antes["version"] and depois["content"] == antes["content"]


@requires_db
def test_banco_guarda_o_titulo_de_cada_documento(limpo):
    context_store.bootstrap(limpo)
    titulos = {d.slug: d.title for d in limpo.query(ContextDocument)}
    assert titulos["project-context"].startswith("Contexto Geral")


@requires_db
def test_backup_exporta_e_restaura_com_historico(limpo, tmp_path):
    from app.jobs import context_backup

    context_store.bootstrap(limpo)
    context_store.salvar(limpo, "features", "# Features\n\nminha edição", note="editei")
    limpo.commit()
    arquivo = tmp_path / "backup.json"
    assert context_backup.exportar(arquivo) == len(context_store._da_semente())

    # o reset: volta tudo ao conteúdo inicial
    limpo.execute(text("DELETE FROM context_document_versions"))
    limpo.execute(text("DELETE FROM context_documents"))
    limpo.commit()
    context_store.bootstrap(limpo)
    limpo.commit()
    assert "minha edição" not in context_store.obter(limpo, "features").content

    context_backup.importar(arquivo)

    limpo.expire_all()
    doc = context_store.obter(limpo, "features")
    assert doc.content.endswith("minha edição") and doc.version == 2
    assert [v.note for v in context_store.historico(limpo, "features")][0] == "editei"


def test_sem_backup_importar_nao_faz_nada(tmp_path):
    from app.jobs import context_backup

    assert context_backup.importar(tmp_path / "nao-existe.json") == 0
