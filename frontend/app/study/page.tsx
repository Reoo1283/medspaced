"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import Protected from "@/components/Protected";
import { Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { ReviewResult, StudyItem } from "@/lib/types";

type AnswerState = Record<string, string | number>;

function StudyScreen() {
  const [items, setItems] = useState<StudyItem[] | null>(null);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState<AnswerState>({});
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);

  const load = useCallback(async () => {
    setItems(null);
    setFinished(false);
    setIndex(0);
    setResult(null);
    setError(null);
    try {
      const due = await api<StudyItem[]>("/study/due?limit=20");
      setItems(due);
      setStartedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tekrar kuyruğu yüklenemedi");
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const item = items && index < items.length ? items[index] : null;

  useEffect(() => {
    setAnswer({});
    setResult(null);
    setStartedAt(Date.now());
  }, [index]);

  function nextCard() {
    if (!items) return;
    if (index + 1 < items.length) {
      setIndex(index + 1);
    } else {
      setFinished(true);
      setItems([]);
    }
  }

  async function submit() {
    if (!item) return;
    setBusy(true);
    setError(null);
    try {
      let payload: Record<string, unknown>;
      if (item.type === "mcq") {
        payload = { option_index: answer.option_index };
      } else if (item.type === "cloze" || item.type === "vignette") {
        payload = { text: answer.text ?? "" };
      } else {
        const left = item.payload.left ?? [];
        payload = {
          pairs: Object.fromEntries(left.map((value) => [value, answer[value] ?? ""])),
        };
      }
      const response = await api<ReviewResult>("/study/reviews", {
        method: "POST",
        body: JSON.stringify({
          exercise_id: item.exercise_id,
          answer: payload,
          response_time_ms: Date.now() - startedAt,
        }),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cevap gönderilemedi");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = (() => {
    if (!item || result) return false;
    if (item.type === "mcq") return typeof answer.option_index === "number";
    if (item.type === "cloze") return String(answer.text ?? "").trim().length > 0;
    if (item.type === "vignette") return String(answer.text ?? "").trim().length >= 10;
    const left = item.payload.left ?? [];
    return left.length > 0 && left.every((value) => answer[value]);
  })();

  const correctAnswer = (result?.correct_answer ?? null) as
    | {
        option_index?: number;
        text?: string;
        pairs?: { left: string; right: string }[];
        model_answer?: string;
        score?: number;
        criteria?: { label: string; score: number; feedback: string }[];
      }
    | null;

  return (
    <>
      <PageHeader
        title="Tekrar"
        description="Bugünkü kartlarınız, unutma eğrinize göre sıralandı."
        actions={
          <button className="btn btn-ghost" onClick={load} disabled={items === null}>
            Yenile
          </button>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}

      {items === null ? (
        <div className="card muted">Kartlar yükleniyor…</div>
      ) : finished ? (
        <div className="card study-shell" style={{ textAlign: "center" }}>
          <h2>Bugünlük tamam 🎉</h2>
          <p className="muted">
            Tekrar kuyruğunuz boş. Yarın yeni kartlar sizi bekliyor olacak.
          </p>
          <div className="row" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary" href="/skills">
              Yeteneklerime bak
            </Link>
            <Link className="btn btn-ghost" href="/">
              Panele dön
            </Link>
          </div>
        </div>
      ) : items.length === 0 ? (
        <div className="card study-shell">
          <Empty>
            Şu an tekrar edilecek kart yok. Yeni sorular onaylandığında burada
            görünecek.
          </Empty>
          <div className="row" style={{ justifyContent: "center", marginTop: 16 }}>
            <Link className="btn btn-ghost" href="/">
              Panele dön
            </Link>
          </div>
        </div>
      ) : item ? (
        <div className="card study-shell">
          <div className="study-meta">
            <span className={`badge badge-${item.type}`}>{item.type}</span>
            <span className="muted small">
              Kart {index + 1} / {items.length} · {item.skill_title ?? "Genel"}
            </span>
          </div>
          <div className="meter">
            <span style={{ width: `${((index + (result ? 1 : 0)) / items.length) * 100}%` }} />
          </div>

          {item.type === "mcq" ? (
            <>
              <p className="prompt">{item.payload.stem}</p>
              <div>
                {(item.payload.options ?? []).map((option, optionIndex) => {
                  const selected = answer.option_index === optionIndex;
                  let className = "option";
                  if (selected) className += " selected";
                  if (result && correctAnswer?.option_index === optionIndex) {
                    className += " correct";
                  } else if (
                    result &&
                    selected &&
                    correctAnswer?.option_index !== optionIndex
                  ) {
                    className += " wrong";
                  }
                  return (
                    <button
                      key={optionIndex}
                      className={className}
                      disabled={Boolean(result)}
                      onClick={() => setAnswer({ option_index: optionIndex })}
                    >
                      {String.fromCharCode(65 + optionIndex)}. {option}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}

          {item.type === "cloze" ? (
            <>
              <p className="prompt">{item.payload.text?.replace("{{blank}}", "_____")}</p>
              <input
                className="input"
                placeholder="Boşluğu doldurun"
                value={String(answer.text ?? "")}
                disabled={Boolean(result)}
                onChange={(event) => setAnswer({ text: event.target.value })}
              />
            </>
          ) : null}

          {item.type === "vignette" ? (
            <>
              <p className="prompt">{item.payload.vignette}</p>
              <p className="muted">{item.payload.prompt}</p>
              <textarea
                className="textarea"
                rows={7}
                placeholder="Klinik kararınızı ve gerekçenizi yazın…"
                value={String(answer.text ?? "")}
                disabled={Boolean(result)}
                onChange={(event) => setAnswer({ text: event.target.value })}
              />
            </>
          ) : null}

          {item.type === "matching" ? (
            <div className="pairs">
              {(item.payload.left ?? []).map((leftValue) => (
                <div className="pair-row" key={leftValue}>
                  <span>{leftValue}</span>
                  <select
                    className="select"
                    value={String(answer[leftValue] ?? "")}
                    disabled={Boolean(result)}
                    onChange={(event) =>
                      setAnswer((current) => ({ ...current, [leftValue]: event.target.value }))
                    }
                  >
                    <option value="">Seçin…</option>
                    {(item.payload.right ?? []).map((rightValue) => (
                      <option key={rightValue} value={rightValue}>
                        {rightValue}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          ) : null}

          {result ? (
            <div className={result.is_correct ? "success-box" : "error-box"} style={{ marginTop: 18 }}>
              <strong>{result.is_correct ? "Doğru!" : "Tekrar gerekiyor"}</strong>
              <div className="small" style={{ marginTop: 4 }}>
                {result.explanation ?? ""}
              </div>
              {item.type === "mcq" && correctAnswer ? (
                <div className="small" style={{ marginTop: 6 }}>
                  Doğru cevap: {item.payload.options?.[Number(correctAnswer.option_index ?? 0)]}
                </div>
              ) : null}
              {item.type === "cloze" && correctAnswer?.text ? (
                <div className="small" style={{ marginTop: 6 }}>
                  Doğru cevap: {correctAnswer.text}
                </div>
              ) : null}
              {item.type === "vignette" ? (
                <div className="small" style={{ marginTop: 6 }}>
                  {correctAnswer?.model_answer ? (
                    <div>
                      <strong>Örnek cevap:</strong> {correctAnswer.model_answer}
                    </div>
                  ) : null}
                  {Array.isArray(correctAnswer?.criteria)
                    ? correctAnswer.criteria.map((criterion) => (
                        <div key={criterion.label}>
                          {criterion.score >= 0.5 ? "✓" : "✗"} {criterion.label} (
                          {Math.round(criterion.score * 100)}%)
                        </div>
                      ))
                    : null}
                </div>
              ) : null}
              {item.type === "matching" && correctAnswer?.pairs ? (
                <ul className="small" style={{ marginTop: 6 }}>
                  {correctAnswer.pairs.map((pair) => (
                    <li key={pair.left}>
                      {pair.left} → {pair.right}
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="small" style={{ marginTop: 8 }}>
                +{result.xp_awarded} XP · Yeni aralık: {result.interval_days} gün ·
                Seviye tahmini: {result.ability_theta.toFixed(2)} · Soru zorluğu:{" "}
                {result.exercise_difficulty.toFixed(2)}
              </div>
            </div>
          ) : null}

          {item.source ? (
            <div className="source">
              <strong>{item.source.filename}</strong> · {item.source.section_title}
              {item.source.page_number ? ` · s. ${item.source.page_number}` : ""}
              <div style={{ marginTop: 6 }}>{item.source.snippet}</div>
            </div>
          ) : null}

          <div className="row" style={{ marginTop: 18, justifyContent: "flex-end" }}>
            {result ? (
              <button className="btn btn-primary" onClick={nextCard}>
                Sonraki kart
              </button>
            ) : (
              <button className="btn btn-primary" onClick={submit} disabled={!canSubmit || busy}>
                {busy ? "Gönderiliyor…" : "Cevabı kontrol et"}
              </button>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

export default function StudyPage() {
  return (
    <Protected>
      <StudyScreen />
    </Protected>
  );
}
