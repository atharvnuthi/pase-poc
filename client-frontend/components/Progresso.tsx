import type { BudgetState } from "@/lib/api";

const COR: Record<BudgetState, string> = {
  ok: "bg-brand-strong",
  atencao: "bg-warning",
  estourado: "bg-danger",
};

/**
 * Barra de progresso. O estado muda a cor, mas nunca é só a cor que o diz: o texto ao
 * lado carrega a mesma informação, para quem não distingue cores.
 */
export default function Progresso({
  percentual,
  estado = "ok",
  rotulo,
}: {
  percentual: number;
  estado?: BudgetState;
  rotulo: string;
}) {
  const largura = Math.max(0, Math.min(percentual, 100));
  return (
    <div
      role="progressbar"
      aria-label={rotulo}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={largura}
      className="h-2 overflow-hidden rounded-sm bg-sunken"
    >
      <div
        className={`h-full rounded-sm transition-[width] duration-500 ${COR[estado]}`}
        style={{ width: `${largura}%` }}
      />
    </div>
  );
}
