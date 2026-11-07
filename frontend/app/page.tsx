"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Personalization, StudyStats } from "@/lib/types";

export default function HomePage() {
  const { user, loading } = useAuth();
  const [stats, setStats] = useState<StudyStats | null>(null);
  const [personalization, setPersonalization] = useState<Personalization | null>(null);
  const [personalizationBusy, setPersonalizationBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rotationName, setRotationName] = useState("");
  const [rotationBusy, setRotationBusy] = useState(false);
  const [rotationMessage, setRotationMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      setStats(null);
      setPersonalization(null);
      return;
    }
    let cancelled = false;
    Promise.all([
      api<StudyStats>("/study/stats"),
      api<Personalization>("/study/personalization"),
    ])
      .then(([data, personal]) => {
        if (!cancelled) {
          setStats(data);
          setRotationName(data.rotation ?? "");
          setPersonalization(personal);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message ?? err));
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  async function optimizePersonalization() {
    setPersonalizationBusy(true);
    setError(null);
    try {
      const data = await api<Personalization>("/study/personalization/optimize", {
        method: "POST",
      });
      setPersonalization(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kişiselleştirme güncellenemedi");
    } finally {
      setPersonalizationBusy(false);
    }
  }

  async function clearRotation() {
    setRotationBusy(true);
    setError(null);
    setRotationMessage(null);
    try {
      await api<{ cleared: boolean }>("/study/rotation", { method: "DELETE" });
      setStats((current) => (current ? { ...current, rotation: null } : current));
      setRotationName("");
      setRotationMessage("Rotasyon odağı kaldırıldı.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rotasyon kaldırılamadı");
    } finally {
      setRotationBusy(false);
    }
  }

  async function saveRotation(event: FormEvent) {
    event.preventDefault();
    const name = rotationName.trim();
    if (name.length < 2) {
      setError("Rotasyon adı en az 2 karakter olmalı");
      return;
    }
    setRotationBusy(true);
    setError(null);
    setRotationMessage(null);
    try {
      const rotation = await api<{ name: string }>("/study/rotation", {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
      setStats((current) => (current ? { ...current, rotation: rotation.name } : current));
      setRotationMessage(`Rotasyon odağı "${rotation.name}" olarak kaydedildi.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rotasyon kaydedilemedi");
    } finally {
      setRotationBusy(false);
    }
  }

  if (loading) {
    return <div className="card muted">Yükleniyor…</div>;
  }

  if (!user) {
    return (
      <>
        <section className="hero">
          <h1>Anestezi bilgisini kalıcı hale getirin.</h1>
          <p>
            Kaynaklarınızdan üretilen, uzman onaylı sorularla aralıklı tekrar
            yapın. Her tekrar, o an unutmaya en yakın olduğunuz kavramı karşınıza
            getirir.
          </p>
          <div className="row">
            <Link className="btn btn-primary btn-lg" href="/register">
              Ücretsiz başla
            </Link>
            <Link className="btn btn-ghost btn-lg" href="/login">
              Giriş yap
            </Link>
          </div>
        </section>

        <div className="grid grid-3">
          <div className="card">
            <h3>Kaynak temelli sorular</h3>
            <p className="muted">
              PDF, DOCX, PPTX ve Markdown dosyalarınız bölümlere ayrılır; her soru
              kaynağındaki chunk ile ilişkilendirilir.
            </p>
          </div>
          <div className="card">
            <h3>Uzman incelemesi</h3>
            <p className="muted">
              Üretilen sorular otomatik olarak inceleme kuyruğuna düşer. Yalnızca
              onaylanan içerik öğrencilere gösterilir.
            </p>
          </div>
          <div className="card">
            <h3>Aralıklı tekrar + XP</h3>
            <p className="muted">
              SM-2 / FSRS zamanlama, yetenek ağacı kilitleri, günlük seri ve XP
              ile ilerlemenizi takip edin.
            </p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={`Merhaba, ${user.full_name || user.email.split("@")[0]}`}
        description="Bugünkü tekrar durumunuz ve hızlı erişim."
        actions={
          <Link className="btn btn-primary" href="/study">
            Çalışmaya başla
          </Link>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}
      <div className="grid grid-stats" style={{ marginBottom: 22 }}>
        <Stat
          label="Bugün tekrar"
          value={stats ? stats.due_count + stats.new_count : "—"}
          hint={stats ? `${stats.due_count} tekrar · ${stats.new_count} yeni` : undefined}
          tone="accent"
        />
        <Stat label="Seri" value={stats ? `${stats.current_streak} gün` : "—"} />
        <Stat label="Toplam XP" value={stats ? stats.total_xp : "—"} hint={stats?.league} />
        <Stat
          label="Ustalaşılan"
          value={stats ? stats.mastered_skill_count : "—"}
          hint="yetenek"
        />
        <Stat
          label="Tahmini seviye"
          value={stats ? stats.ability_theta.toFixed(2) : "—"}
          hint={stats ? `IRT güven ±${stats.ability_se.toFixed(2)}` : undefined}
        />
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="section-title">
          <h2>Rotasyon odağı</h2>
          <span className="badge">{stats?.rotation ?? "kapalı"}</span>
        </div>
        <p className="muted small">
          Aktif rotasyonunuzla eşleşen yetenekler tekrar kuyruğunda öne alınır.
        </p>
        <form className="row" onSubmit={saveRotation} style={{ marginTop: 10 }}>
          <input
            className="input"
            style={{ maxWidth: 360 }}
            placeholder="Örn. Kardiyak anestezi"
            value={rotationName}
            onChange={(event) => setRotationName(event.target.value)}
          />
          <button className="btn btn-primary" disabled={rotationBusy}>
            {rotationBusy ? "Kaydediliyor…" : "Rotasyonu kaydet"}
          </button>
          {stats?.rotation ? (
            <button
              type="button"
              className="btn btn-ghost"
              disabled={rotationBusy}
              onClick={clearRotation}
            >
              Temizle
            </button>
          ) : null}
        </form>
        {rotationMessage ? <div className="success-box small">{rotationMessage}</div> : null}
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="section-title">
          <h2>FSRS kişiselleştirme</h2>
          <span className="badge">
            hedef %{Math.round((personalization?.desired_retention ?? 0.9) * 100)}
          </span>
        </div>
        <p className="muted small">
          Tekrar geçmişinize göre hedef hatırlama oranı uyarlanır. Daha fazla tekrar
          kaydı daha isabetli sonuç verir.
        </p>
        <div className="row" style={{ marginTop: 10 }}>
          <span className="muted small">
            {personalization?.reviews_analyzed
              ? `${personalization.reviews_analyzed} tekrar incelendi · doğruluk %${Math.round(
                  (personalization.accuracy ?? 0) * 100,
                )}${
                  personalization.parameter_count
                    ? ` · ${personalization.parameter_count} FSRS parametresi`
                    : ""
                }`
              : "Henüz tekrar geçmişi yok"}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={optimizePersonalization}
            disabled={personalizationBusy}
          >
            {personalizationBusy ? "Güncelleniyor…" : "Parametreleri güncelle"}
          </button>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h2>Bugünkü plan</h2>
          <p className="muted">
            {stats && stats.due_count + stats.new_count > 0
              ? `Tekrar kuyruğunuzda ${stats.due_count + stats.new_count} kart var.`
              : "Şu an tekrar edilecek kart yok. Yeni içerik üretmek için eğitmeninizle iletişime geçin."}
          </p>
          <div className="row">
            <Link className="btn btn-primary" href="/study">
              Tekrara git
            </Link>
            <Link className="btn btn-ghost" href="/skills">
              Yetenek ağacı
            </Link>
          </div>
        </div>
        <div className="card">
          <h2>Bugünkü aktivite</h2>
          <p className="muted">
            {stats
              ? `${stats.reviews_today} tekrar tamamladınız. Onaylı soru sayısı: ${stats.approved_exercise_count}.`
              : "İstatistikler yükleniyor…"}
          </p>
          <p className="muted small">
            En uzun seriniz: {stats?.longest_streak ?? 0} gün · Haftalık XP:{" "}
            {stats?.weekly_xp ?? 0}
          </p>
        </div>
      </div>
    </>
  );
}
