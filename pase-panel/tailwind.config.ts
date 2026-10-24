import type { Config } from "tailwindcss";

/** Cor a partir de um token de `globals.css`, preservando o modificador de opacidade. */
const token = (nome: string) => `rgb(var(--${nome}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        sunken: token("sunken"),
        line: token("line"),
        "line-strong": token("line-strong"),
        ink: token("ink"),
        "ink-2": token("ink-2"),
        "ink-3": token("ink-3"),
        signal: token("signal"),
        ok: token("ok"),
        warn: token("warn"),
        bad: token("bad"),
        info: token("info"),
        zone: token("zone"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        display: ['"Instrument Serif"', "Georgia", "serif"],
      },
      borderRadius: {
        DEFAULT: "4px",
        sm: "3px",
      },
    },
  },
  plugins: [],
};

export default config;
