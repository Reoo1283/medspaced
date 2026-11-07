"use client";

import { useEffect, useState } from "react";

import Protected from "@/components/Protected";
import { PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import type { ExamQuestion, ExamResult, ExamSession } from "@/lib/types";

type AnswerState = Record<
  string,
  { option_index?: number; text?: string; pairs?: Record<string, string> }
>;

function formatRemaining(milliseconds: number) {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function ExamScreen() {
  const [count, setCount] = useState(10);
  const [minutes, setMinutes] = useState(30);
  const [session, setSession] = useState<ExamSession | null>(null);
  const [answers, setAnswers] = useState<AnswerState>({});
  const [result, setResult] = useState<ExamResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const remaining = session ? new Date(session.expires_at).getTime() - now : 0;

  function updateAnswer(id: string, patch: Partial<AnswerState[string]>) {
    setAnswers((current) => ({
      ...current,
      [id]: { ...current[id], ...patch },
    }));
  }

  function updatePair(id: string, left: string, right: string) {
    setAnswers((current) => ({
      ...current,
      [id]: {
        ...current[id],
        pairs: { ...current[id]?.pairs, [left]: right },
      },
    }));
  }

  async function start() {
    setBusy(true);
    setError(null);
    setResult(null);
    setAnswers({});
    try {
      const data = await api<ExamSession>("/exam/start", {
        method: "POST",
        body: JSON.stringify({ count, duration_minutes: minutes }),
      });
      setSession(data);
      setNow(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sınav başlatılamadı");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api<ExamResult>("/exam/submit", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          answers: Object.entries(answers).map(([exercise_id, answer]) => ({
            exercise_id,
            answer:
              answer.option_index !== undefined
                ? { option_index: answer.option_index }
                : answer.pairs
                  ? { pairs: answer.pairs }
                  : { text: answer.text ?? "" },
          })),
        }),
      });
      setResult(data);
      setSession(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sınav gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  function answered(question: ExamQuestion) {
    const answer = answers[question.exercise_id];
    if (!answer) return false;
    if (question.type === "mcq") return answer.option_index !== undefined;
    if (question.type === "matching") {
      return (question.payload.left ?? []).every((left) => answer.pairs?.[left]);
    }
    return String(answer.text ?? "").trim().length > 0;
  }

  return (
    <>
      <PageHeader
        title="Sınav simülasyonu"
        description="Zamanlı, karışık soru setiyle kendinizi sınayın."
        actions={
          session ? (
            <span className={`badge ${remaining <= 60000 ? "badge-rejected" : "badge-approved"}`}>
              Kalan {formatRemaining(remaining)}
            </span>
          ) : null
        }
      />
      {error ? <div className="error-box">{error}</div> : null}

      {result ? (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="section-title">
            <h2>Sınav sonucu</h2>
            <span className="badge badge-approved">{result.score}%</span>
          </div>
          <div className="grid grid-3" style={{ marginBottom: 14 }}>
            <Stat label="Doğru" value={`${result.correct_count} / ${result.total}`} />
            <Stat label="Kazanılan XP" value={`+${result.xp_awarded}`} />
            <Stat label="Süre" value={`${Math.floor(result.duration_seconds / 60)} dk`} />
          </div>
          <div className="review-list">
            {result.details.map((detail, index) => (
              <div key={detail.exercise_id} className="card">
                <div className="row">
                  <span className={`badge ${detail.is_correct ? "badge-approved" : "badge-rejected"}`}>
                    Soru {index + 1}: {detail.is_correct ? "doğru" : "yanlış"}
                  </span>
                  {detail.score !== null ? (
                    <span className="muted small">rubrik {Math.round(detail.score * 100)}%</span>
                  ) : null}
                </div>
                <p className="small">{detail.explanation ?? ""}</p>
              </div>
            ))}
          </div>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-primary" onClick={() => setResult(null)}>
              Yeni sınav
            </button>
          </div>
        </div>
      ) : null}

      {!session && !result ? (
        <div className="card" style={{ maxWidth: 560 }}>
          <h2>Sınav ayarları</h2>
          <div className="field">
            <label>Soru sayısı</label>
            <input
              className="input"
              type="number"
              min={3}
              max={50}
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label>Süre (dakika)</label>
            <input
              className="input"
              type="number"
              min={5}
              max={180}
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
            />
          </div>
          <button className="btn btn-primary" onClick={start} disabled={busy}>
            {busy ? "Hazırlanıyor…" : "Sınavı başlat"}
          </button>
        </div>
      ) : null}

      {session ? (
        <>
          <div className="row" style={{ marginBottom: 14 }}>
            <span className="badge">{session.questions.length} soru</span>
            <span className="muted small">
              {session.questions.filter(answered).length} / {session.questions.length} cevaplandı
            </span>
          </div>
          <div className="review-list">
            {session.questions.map((question, index) => {
              const answer = answers[question.exercise_id] ?? {};
              return (
                <div className="card" key={question.exercise_id}>
                  <div className="section-title">
                    <div className="row">
                      <span className="badge">Soru {index + 1}</span>
                      <span className="badge">{question.type}</span>
                      <span className="muted small">{question.skill_title ?? "Genel"}</span>
                    </div>
                  </div>
                  {question.type === "mcq" ? (
                    <>
                      <p className="prompt">{question.payload.stem}</p>
                      <div>
                        {(question.payload.options ?? []).map((option, optionIndex) => (
                          <button
                            key={optionIndex}
                            className={`option ${answer.option_index === optionIndex ? "selected" : ""}`}
                            onClick={() =>
                              updateAnswer(question.exercise_id, { option_index: optionIndex })
                            }
                          >
                            {String.fromCharCode(65 + optionIndex)}. {option}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : null}
                  {question.type === "cloze" ? (
                    <>
                      <p className="prompt">{question.payload.text?.replace("{{blank}}", "_____")}</p>
                      <input
                        className="input"
                        placeholder="Boşluğu doldurun"
                        value={String(answer.text ?? "")}
                        onChange={(event) =>
                          updateAnswer(question.exercise_id, { text: event.target.value })
                        }
                      />
                    </>
                  ) : null}
                  {question.type === "vignette" ? (
                    <>
                      <p className="prompt">{question.payload.vignette}</p>
                      <p className="muted">{question.payload.prompt}</p>
                      <textarea
                        className="textarea"
                        rows={6}
                        placeholder="Klinik kararınızı ve gerekçenizi yazın…"
                        value={String(answer.text ?? "")}
                        onChange={(event) =>
                          updateAnswer(question.exercise_id, { text: event.target.value })
                        }
                      />
                    </>
                  ) : null}
                  {question.type === "matching" ? (
                    <div className="pairs">
                      {(question.payload.left ?? []).map((left) => (
                        <div className="pair-row" key={left}>
                          <span>{left}</span>
                          <select
                            className="select"
                            value={answer.pairs?.[left] ?? ""}
                            onChange={(event) =>
                              updatePair(question.exercise_id, left, event.target.value)
                            }
                          >
                            <option value="">Seçin…</option>
                            {(question.payload.right ?? []).map((right) => (
                              <option key={right} value={right}>
                                {right}
                              </option>
                            ))}
                          </select>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 18 }}>
            <button className="btn btn-ghost" onClick={() => setSession(null)} disabled={busy}>
              Vazgeç
            </button>
            <button className="btn btn-primary" onClick={submit} disabled={busy || remaining <= 0}>
              {busy ? "Değerlendiriliyor…" : "Sınavı bitir"}
            </button>
          </div>
        </>
      ) : null}
    </>
  );
}

export default function ExamPage() {
  return (
    <Protected>
      <ExamScreen />
    </Protected>
  );
}
