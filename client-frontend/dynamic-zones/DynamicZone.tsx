"use client";

/**
 * SDK da Zona Dinâmica (SPEC-05 §5).
 *
 *   <DynamicZone slot="resumo_financeiro" userId={userId}>
 *     <ResumoNativo />
 *   </DynamicZone>
 *
 * Os children são o fallback, e o fallback é o caminho normal: a maioria dos
 * usuários não tem personalização e vê o componente nativo. Qualquer coisa que
 * dê errado - 204, rede fora, schema recusado, widget desconhecido, exceção no
 * render - cai neles. A zona nunca deixa a tela quebrada.
 *
 * A personalização é reversível ao padrão (R3): ao lado da etiqueta "personalizado"
 * a pessoa tem "voltar ao padrão", que revoga o payload no core e devolve a zona aos
 * children. A escolha fica gravada - a regra automática não personaliza de novo.
 */

import { Component, type ReactNode, useEffect, useState } from "react";

import { descreverErro, zonePayloadSchema, type ZonePayload } from "./schema";
import { WIDGETS } from "./widgets";

const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL ?? "http://localhost:8000";

/** Avisa o core que um payload foi recusado. Fire-and-forget (§5.4). */
function reportarViolacao(
  userId: number,
  slot: string,
  reason: string,
  rawPayload: unknown,
): void {
  void fetch(`${CORE_URL}/api/upa/violations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      slot,
      reason,
      raw_payload: rawPayload ?? null,
    }),
    keepalive: true,
  }).catch(() => {
    /* se nem o aviso passa, o fallback já está na tela de qualquer forma */
  });
}

/** Revoga o payload em nome da pessoa. Devolve se o core confirmou. */
async function revogarPelaPessoa(userId: number, payloadId: number): Promise<boolean> {
  try {
    const resposta = await fetch(`${CORE_URL}/api/upa/payloads/${payloadId}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ por: "usuario", user_id: userId }),
    });
    return resposta.ok;
  } catch {
    return false;
  }
}

/**
 * Última linha: uma exceção dentro do widget não pode derrubar o dashboard.
 * Ela também é violação - o payload levou o componente a quebrar.
 */
class LimiteDeRender extends Component<
  { onError: (mensagem: string) => void; fallback: ReactNode; children: ReactNode },
  { quebrou: boolean }
> {
  state = { quebrou: false };

  static getDerivedStateFromError() {
    return { quebrou: true };
  }

  componentDidCatch(erro: Error) {
    this.props.onError(`exceção ao renderizar o widget: ${erro.message}`);
  }

  render() {
    return this.state.quebrou ? this.props.fallback : this.props.children;
  }
}

export default function DynamicZone({
  slot,
  userId,
  children,
}: {
  slot: string;
  userId: number;
  children: ReactNode;
}) {
  const [payload, setPayload] = useState<ZonePayload | null>(null);
  const [payloadId, setPayloadId] = useState<number | null>(null);
  const [revogacaoFalhou, setRevogacaoFalhou] = useState(false);

  useEffect(() => {
    let cancelado = false;
    // Outra zona ou outra pessoa: o payload anterior não vale mais para esta.
    setPayload(null);
    setPayloadId(null);
    setRevogacaoFalhou(false);

    async function carregar() {
      let bruto: unknown = null;
      try {
        const resposta = await fetch(
          `${CORE_URL}/api/upa/zones/${slot}/payload?user_id=${userId}`,
          { cache: "no-store" },
        );

        // 204 é o caminho normal: este usuário não tem personalização.
        if (resposta.status === 204 || !resposta.ok) return;

        const corpo = await resposta.json();
        bruto = corpo?.payload;

        const resultado = zonePayloadSchema.safeParse(bruto);
        if (!resultado.success) {
          reportarViolacao(userId, slot, descreverErro(resultado.error), bruto);
          return;
        }

        if (!(resultado.data.widget in WIDGETS)) {
          reportarViolacao(
            userId,
            slot,
            `widget desconhecido no registry do cliente: ${resultado.data.widget}`,
            bruto,
          );
          return;
        }

        if (!cancelado) {
          setPayload(resultado.data);
          setPayloadId(typeof corpo?.payload_id === "number" ? corpo.payload_id : null);
        }
      } catch (erro) {
        // Rede fora ou JSON malformado: só o fallback, sem violação - não houve
        // payload recusado, houve ausência de resposta.
        if (bruto !== null) {
          reportarViolacao(userId, slot, `resposta inesperada: ${String(erro)}`, bruto);
        }
      }
    }

    void carregar();
    return () => {
      cancelado = true;
    };
  }, [slot, userId]);

  if (!payload) return <>{children}</>;

  const Widget = WIDGETS[payload.widget];

  // Sem o id não há o que revogar no core: a ação não aparece em vez de fingir.
  const voltarAoPadrao =
    payloadId === null
      ? undefined
      : async () => {
          setRevogacaoFalhou(false);
          if (await revogarPelaPessoa(userId, payloadId)) {
            setPayload(null);
            setPayloadId(null);
          } else {
            setRevogacaoFalhou(true);
          }
        };

  return (
    <LimiteDeRender
      fallback={children}
      onError={(mensagem) => reportarViolacao(userId, slot, mensagem, payload)}
    >
      <Widget payload={payload} voltarAoPadrao={voltarAoPadrao} />
      {revogacaoFalhou && (
        <p role="status" className="mt-2 text-xs text-danger">
          Não foi possível voltar ao padrão agora. Tente de novo em instantes.
        </p>
      )}
    </LimiteDeRender>
  );
}
