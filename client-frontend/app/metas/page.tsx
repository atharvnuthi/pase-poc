"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import Progresso from "@/components/Progresso";
import { Botao, Campo, Cartao, ENTRADA, TituloSecao, Vazio } from "@/components/ui";
import DynamicZone from "@/dynamic-zones/DynamicZone";
import {
  api,
  formatDate,
  formatMoney,
  listaOuVazia,
  ValidationError,
  type Goal,
} from "@/lib/api";

const HOJE = new Date().toISOString().slice(0, 10);

export default function Metas() {
  return <AppShell>{(persona) => <Conteudo userId={persona.id} />}</AppShell>;
}

function Conteudo({ userId }: { userId: number }) {
  const [metas, setMetas] = useState<Goal[] | null>(null);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);

  const [nome, setNome] = useState("");
  const [alvo, setAlvo] = useState("");
  const [prazo, setPrazo] = useState("");

  // Aporte por meta: o valor digitado e o erro, cada um no seu cartão.
  const [aportes, setAportes] = useState<Record<number, string>>({});
  const [errosDeAporte, setErrosDeAporte] = useState<Record<number, string>>({});

  const recarregar = useCallback(() => {
    api
      .goals(userId)
      .then((v) => setMetas(listaOuVazia<Goal>(v)))
      .catch(() => setMetas([]));
  }, [userId]);

  useEffect(() => {
    recarregar();
  }, [recarregar]);

  async function criar(event: React.FormEvent) {
    event.preventDefault();
    setSalvando(true);
    setErros({});
    try {
      await api.createGoal({
        user_id: userId,
        name: nome,
        target_amount: alvo,
        deadline: prazo || null,
      });
      setNome("");
      setAlvo("");
      setPrazo("");
      recarregar();
    } catch (error) {
      setErros(
        error instanceof ValidationError
          ? error.fields
          : { geral: "Não consegui salvar. Tente de novo." },
      );
    } finally {
      setSalvando(false);
    }
  }

  async function guardar(meta: Goal) {
    setErrosDeAporte((atual) => ({ ...atual, [meta.id]: "" }));
    try {
      await api.contributeToGoal(meta.id, aportes[meta.id] ?? "");
      setAportes((atual) => ({ ...atual, [meta.id]: "" }));
      recarregar();
    } catch (error) {
      const mensagem =
        error instanceof ValidationError
          ? (error.fields.amount ?? "Valor inválido.")
          : "Não consegui guardar. Tente de novo.";
      setErrosDeAporte((atual) => ({ ...atual, [meta.id]: mensagem }));
    }
  }

  async function excluir(meta: Goal) {
    try {
      await api.deleteGoal(meta.id);
      recarregar();
    } catch {
      setErrosDeAporte((atual) => ({ ...atual, [meta.id]: "Não consegui excluir." }));
    }
  }

  return (
    <div className="space-y-6">
      <DynamicZone slot="metas_incentivo" userId={userId}>
        {null}
      </DynamicZone>

      <Cartao>
        <TituloSecao
          titulo="Suas metas"
          apoio="Quanto você quer juntar, quanto já guardou e o ritmo para chegar lá."
        />

        {metas === null ? (
          <p className="px-6 py-10 text-sm text-ink-muted">Carregando…</p>
        ) : metas.length === 0 ? (
          <Vazio>Você ainda não tem metas. Crie a primeira logo abaixo.</Vazio>
        ) : (
          <ul className="divide-y divide-line">
            {metas.map((meta) => (
              <li key={meta.id} className="px-6 py-5">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <h3 className="font-medium">{meta.name}</h3>
                  {meta.reached && (
                    <span className="rounded-md bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-ink">
                      meta atingida
                    </span>
                  )}
                  <span className="tnum ml-auto text-sm text-ink-muted">
                    {formatMoney(meta.saved_amount)} de {formatMoney(meta.target_amount)}
                  </span>
                </div>

                <div className="mt-3">
                  <Progresso percentual={meta.percent} rotulo={`Progresso de ${meta.name}`} />
                </div>

                <p className="tnum mt-2 text-sm text-ink-muted">
                  {meta.reached
                    ? "Você chegou lá."
                    : `Faltam ${formatMoney(meta.remaining)} (${meta.percent}% guardado).`}
                  {meta.deadline && !meta.reached && meta.monthly_needed && (
                    <>
                      {" "}
                      Guardando {formatMoney(meta.monthly_needed)} por mês você chega lá até{" "}
                      {formatDate(meta.deadline)}.
                    </>
                  )}
                </p>

                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <label className="block">
                    <span className="sr-only">{`Valor a guardar em ${meta.name}`}</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Valor a guardar"
                      aria-label={`Valor a guardar em ${meta.name}`}
                      value={aportes[meta.id] ?? ""}
                      onChange={(e) =>
                        setAportes((atual) => ({ ...atual, [meta.id]: e.target.value }))
                      }
                      className={`${ENTRADA} tnum h-9 w-40`}
                    />
                  </label>
                  <Botao
                    tamanho="sm"
                    aria-label={`Guardar em ${meta.name}`}
                    disabled={!aportes[meta.id]}
                    onClick={() => void guardar(meta)}
                  >
                    Guardar
                  </Botao>
                  <Botao
                    variante="perigo"
                    tamanho="sm"
                    className="ml-auto"
                    aria-label={`Excluir meta ${meta.name}`}
                    onClick={() => void excluir(meta)}
                  >
                    Excluir
                  </Botao>
                </div>
                {errosDeAporte[meta.id] && (
                  <p className="mt-2 text-xs font-medium text-danger">{errosDeAporte[meta.id]}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Cartao>

      <Cartao>
        <TituloSecao titulo="Nova meta" apoio="O prazo é opcional; com ele, mostramos quanto guardar por mês." />
        <form onSubmit={criar} className="grid gap-4 p-6 sm:grid-cols-3">
          <Campo label="Nome da meta" erro={erros.name}>
            <input
              required
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Viagem"
              className={ENTRADA}
            />
          </Campo>

          <Campo label="Valor da meta" erro={erros.target_amount}>
            <input
              required
              type="number"
              step="0.01"
              min="0"
              value={alvo}
              onChange={(e) => setAlvo(e.target.value)}
              placeholder="0,00"
              className={`${ENTRADA} tnum`}
            />
          </Campo>

          <Campo label="Prazo (opcional)" erro={erros.deadline}>
            <input
              type="date"
              min={HOJE}
              value={prazo}
              onChange={(e) => setPrazo(e.target.value)}
              className={`${ENTRADA} tnum`}
            />
          </Campo>

          {erros.geral && (
            <p className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger sm:col-span-3">
              {erros.geral}
            </p>
          )}

          <div className="sm:col-span-3">
            <Botao type="submit" variante="marca" disabled={salvando}>
              {salvando ? "Salvando…" : "Criar meta"}
            </Botao>
          </div>
        </form>
      </Cartao>
    </div>
  );
}
