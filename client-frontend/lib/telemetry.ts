/**
 * Telemetria de interface → UPA do pase-core (SPEC-02 §2).
 *
 * Fire-and-forget: falha em silêncio. Se o pase-core estiver fora do ar, o
 * FinTrack continua funcionando normalmente - telemetria é insumo de
 * personalização, nunca requisito de funcionamento do app.
 *
 * Isto NÃO é o canal de evolução de código: reclamação de usuário entra por
 * /suporte (SupportTicket) e é lida pela Captação Passiva do Task Layer. São
 * dois canais de observação distintos (SPEC-03 §2).
 */

const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL ?? "http://localhost:8000";

export function trackPageView(userId: number, path: string): void {
  void fetch(`${CORE_URL}/api/upa/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, event: "page_view", path }),
    keepalive: true,
  }).catch(() => {
    /* silêncio proposital */
  });
}
