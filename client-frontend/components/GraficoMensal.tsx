import { formatMonth, formatMoney, type MonthlyTotal } from "@/lib/api";

const LARGURA = 600;
const ALTURA = 200;
const MARGEM_BASE = 28;
const MARGEM_TOPO = 12;

/**
 * Receitas e despesas dos últimos meses, em barras.
 *
 * SVG à mão, sem biblioteca de gráficos: são seis pares de barras, e uma dependência
 * nova (que o guia de engenharia proíbe sem pedido) custaria mais do que desenha.
 * A tabela escondida existe para leitor de tela: um gráfico sem ela é uma imagem muda.
 */
export default function GraficoMensal({ dados }: { dados: MonthlyTotal[] }) {
  const maior = Math.max(
    ...dados.flatMap((d) => [Number(d.income), Number(d.expense)]),
    0,
  );

  if (dados.length === 0 || maior === 0) {
    return <p className="text-sm text-ink-subtle">Sem movimento nos últimos meses.</p>;
  }

  const areaUtil = ALTURA - MARGEM_BASE - MARGEM_TOPO;
  const larguraDoGrupo = LARGURA / dados.length;
  const larguraDaBarra = Math.min(larguraDoGrupo * 0.32, 34);

  const altura = (valor: string) => (Number(valor) / maior) * areaUtil;

  return (
    <figure>
      <svg
        viewBox={`0 0 ${LARGURA} ${ALTURA}`}
        role="img"
        aria-label={`Receitas e despesas dos últimos ${dados.length} meses`}
        className="h-auto w-full"
      >
        <line
          x1={0}
          x2={LARGURA}
          y1={ALTURA - MARGEM_BASE}
          y2={ALTURA - MARGEM_BASE}
          className="stroke-line"
        />
        {dados.map((d, i) => {
          const centro = larguraDoGrupo * i + larguraDoGrupo / 2;
          const hr = altura(d.income);
          const hd = altura(d.expense);
          return (
            <g key={d.month}>
              <rect
                x={centro - larguraDaBarra - 2}
                y={ALTURA - MARGEM_BASE - hr}
                width={larguraDaBarra}
                height={hr}
                rx={2}
                className="fill-brand-strong"
              />
              <rect
                x={centro + 2}
                y={ALTURA - MARGEM_BASE - hd}
                width={larguraDaBarra}
                height={hd}
                rx={2}
                className="fill-ink-muted"
              />
              <text
                x={centro}
                y={ALTURA - 8}
                textAnchor="middle"
                className="fill-ink-subtle text-[12px]"
              >
                {formatMonth(d.month)}
              </text>
            </g>
          );
        })}
      </svg>

      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-brand-strong" />
          Receitas
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-ink-muted" />
          Despesas
        </span>
      </figcaption>

      <table className="sr-only">
        <caption>Valores de cada mês, em reais</caption>
        <thead>
          <tr>
            <th>Mês</th>
            <th>Receitas</th>
            <th>Despesas</th>
          </tr>
        </thead>
        <tbody>
          {dados.map((d) => (
            <tr key={d.month}>
              <td>{formatMonth(d.month)}</td>
              <td>{formatMoney(d.income)}</td>
              <td>{formatMoney(d.expense)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
