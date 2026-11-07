"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import Protected from "@/components/Protected";
import { Badge, Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { ContentFile, Job, Skill } from "@/lib/types";

interface UploadResponse {
  file: ContentFile;
  job: Job;
}

interface JobResponse {
  job: Job;
}

async function waitForJob(jobId: string): Promise<Job> {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    const job = await api<Job>(`/content/jobs/${jobId}`);
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  throw new Error("İşlem zaman aşımına uğradı");
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

function ContentScreen() {
  const [files, setFiles] = useState<ContentFile[] | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState("");
  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [types, setTypes] = useState({
    mcq: true,
    cloze: true,
    matching: false,
    vignette: false,
  });
  const [maxChunks, setMaxChunks] = useState(10);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [fileList, skillList] = await Promise.all([
        api<ContentFile[]>("/content/files"),
        api<Skill[]>("/skills"),
      ]);
      setFiles(fileList);
      setSkills(skillList);
      const firstExtracted = fileList.find((file) => file.status === "extracted");
      setSelectedFileId((current) => current || firstExtracted?.id || "");
      setSelectedSkillId((current) => current || skillList[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "İçerikler yüklenemedi");
      setFiles([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) {
      setError("Lütfen bir dosya seçin");
      return;
    }
    setBusy("Dosya yükleniyor ve işleniyor…");
    setError(null);
    setMessage(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await api<UploadResponse>("/content/files", {
        method: "POST",
        body,
      });
      const job = await waitForJob(response.job.id);
      if (job.status === "failed") {
        throw new Error(job.message ?? "İçerik işleme başarısız");
      }
      setMessage(`${response.file.filename} yüklendi ve ${job.result?.chunks ?? 0} chunk çıkarıldı.`);
      if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yükleme başarısız");
    } finally {
      setBusy(null);
    }
  }

  async function processFile(file: ContentFile) {
    setBusy(`${file.filename} işleniyor…`);
    setError(null);
    setMessage(null);
    try {
      const response = await api<JobResponse>(`/content/files/${file.id}/process`, {
        method: "POST",
      });
      const job = await waitForJob(response.job.id);
      if (job.status === "failed") throw new Error(job.message ?? "İşleme başarısız");
      setMessage(`${file.filename} yeniden işlendi (${job.result?.chunks ?? 0} chunk).`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşleme başarısız");
    } finally {
      setBusy(null);
    }
  }

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (!selectedFileId || !selectedSkillId) {
      setError("Dosya ve yetenek seçin");
      return;
    }
    const exerciseTypes = Object.entries(types)
      .filter(([, checked]) => checked)
      .map(([name]) => name);
    if (exerciseTypes.length === 0) {
      setError("En az bir egzersiz tipi seçin");
      return;
    }
    setBusy("Sorular üretiliyor…");
    setError(null);
    setMessage(null);
    try {
      const response = await api<JobResponse>(
        `/content/files/${selectedFileId}/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            skill_id: selectedSkillId,
            exercise_types: exerciseTypes,
            max_chunks: maxChunks,
          }),
        },
      );
      const job = await waitForJob(response.job.id);
      if (job.status === "failed") throw new Error(job.message ?? "Üretim başarısız");
      const created = Number(job.result?.exercises_created ?? 0);
      const skipped = Number(job.result?.skipped ?? 0);
      setMessage(
        `${created} soru üretildi, ${skipped} atlandı. Sorular inceleme kuyruğunda.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Üretim başarısız");
    } finally {
      setBusy(null);
    }
  }

  const selectedFile = files?.find((file) => file.id === selectedFileId);

  return (
    <>
      <PageHeader
        title="İçerik yönetimi"
        description="Kaynak yükleyin, chunk'layın ve onay için soru üretin."
        actions={
          <button className="btn btn-ghost" onClick={load} disabled={Boolean(busy)}>
            Yenile
          </button>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}
      {message ? <div className="success-box">{message}</div> : null}
      {busy ? <div className="card card-tight muted">{busy}</div> : null}

      <div className="grid grid-2">
        <form className="card" onSubmit={upload}>
          <h2>Yeni kaynak yükle</h2>
          <p className="muted small">
            PDF, DOCX, PPTX, Markdown veya TXT. Yükleme sonrası metin otomatik
            çıkarılır ve chunk'lanır.
          </p>
          <div className="field">
            <label htmlFor="file">Dosya</label>
            <input
              id="file"
              ref={fileInput}
              className="input"
              type="file"
              accept=".pdf,.docx,.pptx,.md,.markdown,.txt,.text"
              required
            />
          </div>
          <button className="btn btn-primary" disabled={Boolean(busy)}>
            Yükle ve işle
          </button>
        </form>

        <form className="card" onSubmit={generate}>
          <h2>Soru üret</h2>
          <p className="muted small">
            Seçilen dosyanın chunk'larından LLM ile taslak sorular üretilir;
            inceleme kuyruğuna düşer.
          </p>
          <div className="field">
            <label htmlFor="sourceFile">Kaynak dosya</label>
            <select
              id="sourceFile"
              className="select"
              value={selectedFileId}
              onChange={(event) => setSelectedFileId(event.target.value)}
            >
              <option value="">Seçin…</option>
              {(files ?? [])
                .filter((file) => file.status === "extracted")
                .map((file) => (
                  <option key={file.id} value={file.id}>
                    {file.filename} ({file.chunk_count} chunk)
                  </option>
                ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="skill">Yetenek</label>
            <select
              id="skill"
              className="select"
              value={selectedSkillId}
              onChange={(event) => setSelectedSkillId(event.target.value)}
            >
              <option value="">Seçin…</option>
              {skills.map((skill) => (
                <option key={skill.id} value={skill.id}>
                  {skill.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Egzersiz tipleri</label>
            <div className="row">
              {(["mcq", "cloze", "matching", "vignette"] as const).map((name) => (
                <label key={name} className="row small" style={{ gap: 6 }}>
                  <input
                    type="checkbox"
                    checked={types[name]}
                    onChange={(event) =>
                      setTypes((current) => ({ ...current, [name]: event.target.checked }))
                    }
                  />
                  {name}
                </label>
              ))}
            </div>
          </div>
          <div className="field">
            <label htmlFor="maxChunks">Maksimum chunk</label>
            <input
              id="maxChunks"
              className="input"
              type="number"
              min={1}
              max={200}
              value={maxChunks}
              onChange={(event) => setMaxChunks(Number(event.target.value))}
            />
          </div>
          <button className="btn btn-primary" disabled={Boolean(busy) || !selectedFile}>
            Üret
          </button>
        </form>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="section-title">
          <h2>Kaynaklar</h2>
          <span className="muted small">{files?.length ?? 0} dosya</span>
        </div>
        {files === null ? (
          <p className="muted">Yükleniyor…</p>
        ) : files.length === 0 ? (
          <Empty>Henüz kaynak yüklenmedi.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dosya</th>
                  <th>Durum</th>
                  <th>Chunk</th>
                  <th>Soru</th>
                  <th>Tarih</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.id}>
                    <td>
                      <strong>{file.filename}</strong>
                      <div className="muted small">{(file.size_bytes / 1024).toFixed(1)} KB</div>
                    </td>
                    <td>
                      <Badge status={file.status} />
                      {file.error_message ? (
                        <div className="muted small">{file.error_message}</div>
                      ) : null}
                    </td>
                    <td>{file.chunk_count}</td>
                    <td>{file.exercise_count}</td>
                    <td className="muted small">{formatDate(file.created_at)}</td>
                    <td>
                      <div className="row">
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setSelectedFileId(file.id)}
                        >
                          Seç
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => processFile(file)}
                          disabled={Boolean(busy)}
                        >
                          İşle
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

export default function ContentPage() {
  return (
    <Protected roles={["reviewer", "admin"]}>
      <ContentScreen />
    </Protected>
  );
}
