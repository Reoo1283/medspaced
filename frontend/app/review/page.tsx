"use client";

import { useCallback, useEffect, useState } from "react";

import Protected from "@/components/Protected";
import { Badge, Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Exercise, ReviewCounts } from "@/lib/types";

const FILTERS: { key: string; label: string }[] = [
  { key: "draft,under_review", label: "Bekleyen" },
  { key: "under_review", label: "İncelemede" },
  { key: "draft", label: "Taslak" },
  { key: "approved", label: "Onaylı" },
  { key: "rejected", label: "Reddedilen" },
];

function PayloadView({ exercise }: { exercise: Exercise }) {
  const payload = exercise.payload as Record<string, any>;
  if (exercise.type === "mcq") {
    return (
      <div>
        <p className="prompt" style={{ fontSize: "1.05rem" }}>
          {payload.stem}
        </p>
        <ol className="option-list">
          {(payload.options ?? []).map((option: { text: string; is_correct: boolean }, idx: number) => (
            <li key={idx} className={option.is_correct ? "correct" : undefined}>
              {String.fromCharCode(65 + idx)}. {option.text}
              {option.is_correct ? " ✓" : ""}
            </li>
          ))}
        </ol>
      </div>
    );
  }
  if (exercise.type === "vignette") {
    return (
      <div>
        <p className="prompt" style={{ fontSize: "1.05rem" }}>
          {payload.vignette}
        </p>
        <p>{payload.prompt}</p>
        <div className="source">
          <strong>Rubrik</strong>
          <ul>
            {(payload.rubric ?? []).map((criterion: { label: string; description: string; weight: number }) => (
              <li key={criterion.label}>
                {criterion.label} (ağırlık {criterion.weight})
                {criterion.description ? ` — ${criterion.description}` : ""}
              </li>
            ))}
          </ul>
          <div>
            <strong>Örnek cevap:</strong> {payload.model_answer}
          </div>
        </div>
      </div>
    );
  }
  if (exercise.type === "cloze") {
    return (
      <div>
        <p className="prompt" style={{ fontSize: "1.05rem" }}>
          {String(payload.text ?? "").replace("{{blank}}", "_____")}
        </p>
        <p>
          <strong>Cevap:</strong> {payload.answer}
          {Array.isArray(payload.alternatives) && payload.alternatives.length > 0
            ? ` (alternatif: ${payload.alternatives.join(", ")})`
            : ""}
        </p>
      </div>
    );
  }
  return (
    <ul className="pair-list">
      {(payload.pairs ?? []).map((pair: { left: string; right: string }) => (
        <li key={pair.left}>
          <strong>{pair.left}</strong> → {pair.right}
        </li>
      ))}
    </ul>
  );
}

function ReviewScreen() {
  const [statusFilter, setStatusFilter] = useState(FILTERS[0].key);
  const [queue, setQueue] = useState<Exercise[] | null>(null);
  const [counts, setCounts] = useState<ReviewCounts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setQueue(null);
    setError(null);
    try {
      const [items, counters] = await Promise.all([
        api<Exercise[]>(`/review/queue?status=${encodeURIComponent(statusFilter)}&limit=100`),
        api<ReviewCounts>("/review/counts"),
      ]);
      setQueue(items);
      setCounts(counters);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kuyruk yüklenemedi");
      setQueue([]);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function decide(exercise: Exercise, action: "submit" | "approve" | "reject") {
    let note: string | null = null;
    if (action === "reject") {
      note = window.prompt("Red gerekçesi (zorunlu):");
      if (note === null) return;
      if (!note.trim()) {
        setError("Red işlemi için gerekçe zorunludur");
        return;
      }
    }
    setBusyId(exercise.id);
    setError(null);
    try {
      await api(`/review/exercises/${exercise.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ action, note }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem başarısız");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        title="İnceleme kuyruğu"
        description="Üretilen soruları onaylayın veya gerekçesiyle reddedin."
        actions={
          <button className="btn btn-ghost" onClick={load} disabled={queue === null}>
            Yenile
          </button>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}

      {counts ? (
        <div className="row" style={{ marginBottom: 16 }}>
          <span className="badge badge-draft">{counts.draft} taslak</span>
          <span className="badge badge-under_review">{counts.under_review} incelemede</span>
          <span className="badge badge-approved">{counts.approved} onaylı</span>
          <span className="badge badge-rejected">{counts.rejected} reddedilen</span>
        </div>
      ) : null}

      <div className="row" style={{ marginBottom: 18 }}>
        {FILTERS.map((filter) => (
          <button
            key={filter.key}
            className={`btn btn-sm ${statusFilter === filter.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setStatusFilter(filter.key)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {queue === null ? (
        <div className="card muted">Kuyruk yükleniyor…</div>
      ) : queue.length === 0 ? (
        <div className="card">
          <Empty>Bu filtrede soru yok.</Empty>
        </div>
      ) : (
        <div className="review-list">
          {queue.map((exercise) => (
            <div className="card review-card" key={exercise.id}>
              <div className="section-title">
                <div className="row">
                  <span className="badge">{exercise.type}</span>
                  <Badge status={exercise.status} />
                  {exercise.skill_title ? (
                    <span className="muted small">{exercise.skill_title}</span>
                  ) : null}
                </div>
                <span className="muted small">
                  zorluk {exercise.difficulty.toFixed(2)} ·{" "}
                  {new Date(exercise.created_at).toLocaleString("tr-TR", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </span>
              </div>

              <PayloadView exercise={exercise} />

              {exercise.payload?.explanation ? (
                <p className="muted small">
                  <strong>Açıklama:</strong> {String(exercise.payload.explanation)}
                </p>
              ) : null}

              {exercise.source ? (
                <div className="source">
                  <strong>{exercise.source.filename}</strong> · {exercise.source.section_title}
                  {exercise.source.page_number ? ` · s. ${exercise.source.page_number}` : ""}
                  <div style={{ marginTop: 6 }}>{exercise.source.snippet}</div>
                </div>
              ) : null}

              {exercise.rejection_reason ? (
                <div className="error-box" style={{ marginTop: 12 }}>
                  Red gerekçesi: {exercise.rejection_reason}
                </div>
              ) : null}

              {exercise.status === "draft" || exercise.status === "under_review" ? (
                <div className="row" style={{ marginTop: 16, justifyContent: "flex-end" }}>
                  {exercise.status === "draft" ? (
                    <button
                      className="btn btn-ghost"
                      disabled={busyId === exercise.id}
                      onClick={() => decide(exercise, "submit")}
                    >
                      İncelemeye gönder
                    </button>
                  ) : null}
                  <button
                    className="btn btn-danger"
                    disabled={busyId === exercise.id}
                    onClick={() => decide(exercise, "reject")}
                  >
                    Reddet
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={busyId === exercise.id}
                    onClick={() => decide(exercise, "approve")}
                  >
                    Onayla
                  </button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function ReviewPage() {
  return (
    <Protected roles={["reviewer", "admin"]}>
      <ReviewScreen />
    </Protected>
  );
}
