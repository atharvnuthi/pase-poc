import type { Metadata } from "next";

import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";

import "./globals.css";
import { Provedores } from "@/lib/query";

export const metadata: Metadata = {
  title: "PASE - painel de controle",
  description: "Painel de controle humano do PASE",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // O tema escolhido à mão é aplicado no cliente, depois da hidratação.
    <html lang="pt-BR" suppressHydrationWarning>
      <body>
        <Provedores>{children}</Provedores>
      </body>
    </html>
  );
}
