import type { Config } from "tailwindcss";

/**
 * As cores semânticas apontam para as variáveis de `globals.css`. Componentes
 * usam só estes nomes - `bg-white` ou `text-slate-900` cravados são o que impede
 * um tema de mudar num lugar só.
 */
const token = (nome: string) => `rgb(var(--${nome}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./dynamic-zones/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        surface: token("surface"),
        sunken: token("surface-sunken"),
        line: token("line"),
        "line-strong": token("line-strong"),
        ink: {
          DEFAULT: token("ink"),
          muted: token("ink-muted"),
          subtle: token("ink-subtle"),
        },
        brand: {
          DEFAULT: token("brand"),
          strong: token("brand-strong"),
          ink: token("brand-ink"),
        },
        danger: {
          DEFAULT: token("danger"),
          soft: token("danger-soft"),
        },
        warning: {
          DEFAULT: token("warning"),
          soft: token("warning-soft"),
        },
        "danger-on-inverse": token("danger-on-inverse"),
        inverse: token("inverse"),
        "on-inverse": token("on-inverse"),
        "on-ink": token("on-ink"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        display: ['"Instrument Serif"', "Georgia", "Times New Roman", "serif"],
      },
      borderRadius: {
        /* Cantos discretos: o app é um livro de contas, não um brinquedo. */
        lg: "0.375rem",
        xl: "0.5rem",
        "2xl": "0.625rem",
        "3xl": "0.75rem",
      },
      boxShadow: {
        /* Sem sombras de "cartão flutuando": o contorno fino já separa. Ficam só
           o foco e uma elevação para o que de fato sobrepõe (modal). */
        card: "none",
        lift: "0 20px 50px -20px rgb(28 26 22 / 0.35)",
        focus: "0 0 0 3px rgb(var(--brand) / 0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
