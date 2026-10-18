import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MoneyPlant — SME finance copilot",
  description:
    "Deterministic financial simulations, rule-based decision support, and Laya + LLM explanations for small businesses.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-surface text-ink antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
