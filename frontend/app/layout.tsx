import type { Metadata } from "next";

import NavBar from "@/components/NavBar";
import { AuthProvider } from "@/lib/auth";

import "./globals.css";

export const metadata: Metadata = {
  title: "MedSpaced — Anestezi Aralıklı Tekrar",
  description:
    "Anestezi öğrencileri için kaynak temelli, aralıklı tekrar öğrenme platformu.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        <AuthProvider>
          <NavBar />
          <main className="container">{children}</main>
          <footer className="footer">
            MedSpaced · Kaynak temelli tekrar · Tıbbi içerik uzman onayı gerektirir
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
