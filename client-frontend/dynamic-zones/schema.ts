/**
 * Espelho em Zod do contrato canônico (SPEC-05 §6).
 *
 * A fonte de verdade é `docs/contracts/zona.schema.json`. Este
 * arquivo precisa dizer exatamente a mesma coisa - divergência entre os dois é
 * bug, e existe um teste no pase-core (`test_contract_mirror.py`) que traduz este
 * arquivo para JSON Schema e compara os dois campo a campo. Por isso a forma é
 * restrita: `z.object`, `z.string`, `z.number`, `z.enum`, `z.array`, `texto()` e a
 * tabela `OBRIGATORIOS_POR_WIDGET`. Construção fora disso faz o teste falhar.
 *
 * Esta é a validação definitiva (Hard Constraint). O core também valida, mas a
 * palavra final é daqui: é este código que decide se algo vai à tela.
 */

import { z } from "zod";

/** Somente rotas internas do FinTrack. É esta regex que impede link externo. */
export const HREF_INTERNO = /^\/(dashboard|transacoes|relatorios|orcamentos|metas|suporte)$/;

export const LABEL_MAX = 40;
export const MAX_ITEMS = 3;

/**
 * Texto com limite de tamanho contado como o JSON Schema conta: em caracteres
 * (code points). O `.max()` do Zod conta unidades UTF-16, e um emoji vale duas -
 * um rótulo com emoji que o core aceitou seria recusado aqui.
 */
function texto(min: number, max: number) {
  return z.string().refine(
    (valor) => {
      const tamanho = Array.from(valor).length;
      return tamanho >= min && tamanho <= max;
    },
    { message: `deve ter entre ${min} e ${max} caracteres` },
  );
}

const itemSchema = z
  .object({
    label: texto(1, LABEL_MAX),
    href: z.string().regex(HREF_INTERNO),
  })
  .strict();

/** Os condicionais do `allOf` no JSON Schema canônico: o que cada widget exige. */
export const OBRIGATORIOS_POR_WIDGET = {
  shortcut_list: ["maxItems", "items"],
  summary_card: ["maxItems", "items"],
  alert_banner: ["tone"],
} as const;

export const zonePayloadSchema = z
  .object({
    widget: z.enum(["shortcut_list", "summary_card", "alert_banner"]),
    label: texto(1, LABEL_MAX),
    maxItems: z.number().int().min(1).max(MAX_ITEMS).optional(),
    tone: z.enum(["neutral", "atencao"]).optional(),
    items: z.array(itemSchema).max(MAX_ITEMS).optional(),
  })
  .strict()
  .superRefine((valor, ctx) => {
    for (const campo of OBRIGATORIOS_POR_WIDGET[valor.widget]) {
      if (valor[campo] === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [campo],
          message: `${campo} é obrigatório para ${valor.widget}`,
        });
      }
    }
  });

export type ZonePayload = z.infer<typeof zonePayloadSchema>;
export type ZoneItem = z.infer<typeof itemSchema>;

/** Mensagem curta e legível do primeiro problema encontrado. */
export function descreverErro(erro: z.ZodError): string {
  const primeiro = erro.issues[0];
  if (!primeiro) return "payload inválido";
  const caminho = primeiro.path.join(".");
  return caminho ? `${caminho}: ${primeiro.message}` : primeiro.message;
}
