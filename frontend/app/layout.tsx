import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/sidebar";

export const metadata: Metadata = {
  title: "Stock Intelligence Platform",
  description: "Local-first Indian stock-market research, scanning & AI verdicts. No API keys.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 min-w-0 px-6 py-6">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
