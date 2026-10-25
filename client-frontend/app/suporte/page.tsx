"use client";

import { useState } from "react";

import AppShell from "@/components/AppShell";
import { AREA_TEXTO, Botao, Cartao, TituloSecao } from "@/components/ui";
import DynamicZone from "@/dynamic-zones/DynamicZone";
import { api } from "@/lib/api";

/**
 * Canal de suporte. Cada ticket daqui é lido pela Captação Passiva do Task
 * Layer (SPEC-03 §2) - é uma das origens de demanda do modelo PASE.
 */

export default function Suporte() {
  return <AppShell>{(persona) => <Conteudo userId={persona.id} />}</AppShell>;
}

function Conteudo({ userId }: { userId: number }) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(event: React.FormEvent) {
    event.preventDefault();
    if (!texto.trim()) return;

    setEnviando(true);
    setAviso(null);
    setErro(null);
    try {
      await api.createTicket(userId, texto.trim());
      setAviso("Recebemos sua mensagem. Nossa equipe vai olhar!");
      setTexto("");
    } catch {
      setErro("Não consegui enviar agora. Tente de novo em instantes.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
    <DynamicZone slot="suporte_ajuda" userId={userId}>
      {null}
    </DynamicZone>
    <Cartao>
      <TituloSecao
        titulo="Precisa de ajuda?"
        apoio="Conte o que está acontecendo e nós respondemos."
      />

      <form onSubmit={enviar} className="space-y-4 p-6">
        <textarea
          value={texto}
          onChange={(event) => setTexto(event.target.value)}
          rows={5}
          placeholder="Ex.: não encontro onde ver quanto gastei em transporte esse mês"
          className={AREA_TEXTO}
        />

        {aviso && (
          <p className="rounded-xl border border-brand/25 bg-brand/5 px-4 py-3 text-sm text-brand-ink">
            {aviso}
          </p>
        )}
        {erro && (
          <p className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
            {erro}
          </p>
        )}

        <Botao type="submit" variante="marca" disabled={enviando || !texto.trim()}>
          {enviando ? "Enviando…" : "Enviar"}
        </Botao>
      </form>
    </Cartao>
    </div>
  );
}
