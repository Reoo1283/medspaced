"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, password, fullName);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card form-narrow">
      <h1>Kayıt ol</h1>
      <p className="muted">
        Öğrenci hesabı oluşturun; içerik üretimi ve inceleme eğitmen yetkisi
        gerektirir.
      </p>
      {error ? <div className="error-box">{error}</div> : null}
      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="fullName">Ad soyad</label>
          <input
            id="fullName"
            className="input"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="email">E-posta</label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Parola (en az 8 karakter)</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        <button className="btn btn-primary btn-lg" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Hesap oluşturuluyor…" : "Hesap oluştur"}
        </button>
      </form>
      <p className="muted small" style={{ marginTop: 16 }}>
        Zaten hesabınız var mı? <Link href="/login">Giriş yapın</Link>
      </p>
    </div>
  );
}
