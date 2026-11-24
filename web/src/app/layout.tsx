import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NFI X9 — Strategy Command Center",
  description:
    "A modern control surface for NostalgiaForInfinity X9 and Freqtrade: live equity, open risk, pair performance and trade history.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
