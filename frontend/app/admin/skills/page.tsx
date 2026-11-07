"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import Protected from "@/components/Protected";
import { Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Skill, SkillNode } from "@/lib/types";

interface FlatSkill {
  node: SkillNode;
  depth: number;
}

interface EditState {
  id: string;
  title: string;
  category: string;
  description: string;
  parent_id: string;
  prerequisites: string[];
}

function flatten(nodes: SkillNode[], depth = 0): FlatSkill[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...flatten(node.children ?? [], depth + 1),
  ]);
}

function findNode(nodes: SkillNode[], id: string): SkillNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findNode(node.children ?? [], id);
    if (found) return found;
  }
  return null;
}

function collectIds(node: SkillNode | null, result = new Set<string>()): Set<string> {
  if (!node) return result;
  result.add(node.id);
  for (const child of node.children ?? []) collectIds(child, result);
  return result;
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
}

function SkillManager() {
  const [tree, setTree] = useState<SkillNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("genel");
  const [description, setDescription] = useState("");
  const [parentId, setParentId] = useState("");
  const [prerequisites, setPrerequisites] = useState<string[]>([]);

  const [editing, setEditing] = useState<EditState | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setTree(await api<SkillNode[]>("/skills/tree"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yetenekler yüklenemedi");
      setTree([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const flat = useMemo(() => (tree ? flatten(tree) : []), [tree]);
  const titles = useMemo(
    () => new Map(flat.map(({ node }) => [node.id, node.title])),
    [flat],
  );

  const blockedParents = useMemo(() => {
    if (!editing || !tree) return new Set<string>();
    return collectIds(findNode(tree, editing.id));
  }, [editing, tree]);

  async function createSkill(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const created = await api<Skill>("/skills", {
        method: "POST",
        body: JSON.stringify({
          title,
          category,
          description,
          parent_id: parentId || null,
        }),
      });
      for (const prerequisite of prerequisites) {
        await api(`/skills/${created.id}/prerequisites`, {
          method: "POST",
          body: JSON.stringify({ prerequisite_id: prerequisite }),
        });
      }
      setMessage(`"${created.title}" yeteneği oluşturuldu.`);
      setTitle("");
      setDescription("");
      setParentId("");
      setPrerequisites([]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yetenek oluşturulamadı");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(node: SkillNode) {
    setError(null);
    setMessage(null);
    setEditing({
      id: node.id,
      title: node.title,
      category: node.category,
      description: node.description,
      parent_id: node.parent_id ?? "",
      prerequisites: [...node.prerequisites],
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api<Skill>(`/skills/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: editing.title,
          category: editing.category,
          description: editing.description,
          parent_id: editing.parent_id || null,
        }),
      });
      const original = new Set(
        flat.find(({ node }) => node.id === editing.id)?.node.prerequisites ?? [],
      );
      const wanted = new Set(editing.prerequisites);
      for (const prerequisite of original) {
        if (!wanted.has(prerequisite)) {
          await api(`/skills/${editing.id}/prerequisites/${prerequisite}`, {
            method: "DELETE",
          });
        }
      }
      for (const prerequisite of wanted) {
        if (!original.has(prerequisite)) {
          await api(`/skills/${editing.id}/prerequisites`, {
            method: "POST",
            body: JSON.stringify({ prerequisite_id: prerequisite }),
          });
        }
      }
      setMessage(`"${editing.title}" güncellendi.`);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yetenek güncellenemedi");
    } finally {
      setBusy(false);
    }
  }

  async function deleteSkill(node: SkillNode) {
    if (!window.confirm(`"${node.title}" yeteneği silinsin mi?`)) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api(`/skills/${node.id}`, { method: "DELETE" });
      setMessage(`"${node.title}" silindi.`);
      if (editing?.id === node.id) setEditing(null);
      await load();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Silinemedi. Bağlı sorular varsa önce onları taşıyın veya silin.",
      );
    } finally {
      setBusy(false);
    }
  }

  const prerequisiteChoices = flat.filter(({ node }) => node.id !== editing?.id);

  return (
    <>
      <PageHeader
        title="Yetenek ağacı yönetimi"
        description="Konu hiyerarşisini ve önkoşul ilişkilerini tanımlayın."
        actions={
          <>
            <Link className="btn btn-ghost" href="/skills">
              Öğrenci görünümü
            </Link>
            <button className="btn btn-ghost" onClick={load} disabled={tree === null || busy}>
              Yenile
            </button>
          </>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}
      {message ? <div className="success-box">{message}</div> : null}

      <div className="grid grid-2">
        <form className="card" onSubmit={createSkill}>
          <h2>Yeni yetenek</h2>
          <div className="field">
            <label htmlFor="newTitle">Başlık</label>
            <input
              id="newTitle"
              className="input"
              value={title}
              minLength={2}
              onChange={(event) => setTitle(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="newCategory">Kategori</label>
            <input
              id="newCategory"
              className="input"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="newDescription">Açıklama</label>
            <textarea
              id="newDescription"
              className="input"
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="newParent">Üst yetenek</label>
            <select
              id="newParent"
              className="select"
              value={parentId}
              onChange={(event) => setParentId(event.target.value)}
            >
              <option value="">Kök seviye</option>
              {flat.map(({ node }) => (
                <option key={node.id} value={node.id}>
                  {node.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Önkoşullar</label>
            <div className="checkbox-grid">
              {flat.map(({ node }) => (
                <label key={node.id} className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={prerequisites.includes(node.id)}
                    onChange={() => setPrerequisites((current) => toggle(current, node.id))}
                  />
                  {node.title}
                </label>
              ))}
            </div>
          </div>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Yetenek ekle"}
          </button>
        </form>

        <div className="card">
          <h2>Graf özeti</h2>
          <p className="muted small">
            Yetenekler üst-alt ilişkisiyle ağaca, önkoşullarla öğrenme sırasına
            bağlanır. Bir öğrenci, tüm önkoşullarında %70 hakimiyete ulaşmadan
            alt yeteneği açamaz.
          </p>
          <div className="row" style={{ marginBottom: 12 }}>
            <span className="badge">{flat.length} yetenek</span>
            <span className="badge">{tree?.length ?? 0} kök düğüm</span>
          </div>
          {flat.length === 0 ? (
            <Empty>Henüz yetenek yok. Soldaki formdan ilkini ekleyin.</Empty>
          ) : (
            <ul className="list-reset stack">
              {flat.map(({ node, depth }) => (
                <li
                  key={node.id}
                  className="muted small"
                  style={{ paddingLeft: depth * 16 }}
                >
                  {depth > 0 ? "↳ " : ""}
                  <strong style={{ color: "var(--text)" }}>{node.title}</strong> ·{" "}
                  {node.category}
                  {node.prerequisites.length > 0 ? (
                    <> · önkoşul: {node.prerequisites.map((id) => titles.get(id) ?? id).join(", ")}</>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="section-title">
          <h2>Yetenekler</h2>
          <span className="muted small">Düzenlemek için satırdaki butonu kullanın</span>
        </div>
        {tree === null ? (
          <p className="muted">Yükleniyor…</p>
        ) : flat.length === 0 ? (
          <Empty>Kayıtlı yetenek yok.</Empty>
        ) : (
          <div className="stack">
            {flat.map(({ node, depth }) => (
              <div
                key={node.id}
                className="card card-tight manager-row"
                style={{ marginLeft: Math.min(depth, 6) * 18 }}
              >
                <div className="section-title" style={{ marginBottom: 6 }}>
                  <div className="row">
                    <strong>{node.title}</strong>
                    <span className="badge">{node.category}</span>
                    {node.parent_id ? (
                      <span className="muted small">
                        üst: {titles.get(node.parent_id) ?? "—"}
                      </span>
                    ) : (
                      <span className="muted small">kök</span>
                    )}
                  </div>
                  <div className="row">
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => startEdit(node)}
                      disabled={busy}
                    >
                      Düzenle
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => deleteSkill(node)}
                      disabled={busy}
                    >
                      Sil
                    </button>
                  </div>
                </div>
                <p className="muted small" style={{ margin: "4px 0" }}>
                  {node.description || "Açıklama yok"}
                </p>
                <p className="muted small" style={{ margin: 0 }}>
                  Önkoşullar:{" "}
                  {node.prerequisites.length > 0
                    ? node.prerequisites.map((id) => titles.get(id) ?? id).join(", ")
                    : "yok"}
                </p>

                {editing?.id === node.id ? (
                  <form onSubmit={saveEdit} className="manager-form">
                    <div className="grid grid-2">
                      <div className="field">
                        <label htmlFor={`title-${node.id}`}>Başlık</label>
                        <input
                          id={`title-${node.id}`}
                          className="input"
                          value={editing.title}
                          minLength={2}
                          onChange={(event) =>
                            setEditing({ ...editing, title: event.target.value })
                          }
                          required
                        />
                      </div>
                      <div className="field">
                        <label htmlFor={`category-${node.id}`}>Kategori</label>
                        <input
                          id={`category-${node.id}`}
                          className="input"
                          value={editing.category}
                          onChange={(event) =>
                            setEditing({ ...editing, category: event.target.value })
                          }
                          required
                        />
                      </div>
                    </div>
                    <div className="field">
                      <label htmlFor={`description-${node.id}`}>Açıklama</label>
                      <textarea
                        id={`description-${node.id}`}
                        className="input"
                        rows={2}
                        value={editing.description}
                        onChange={(event) =>
                          setEditing({ ...editing, description: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`parent-${node.id}`}>Üst yetenek</label>
                      <select
                        id={`parent-${node.id}`}
                        className="select"
                        value={editing.parent_id}
                        onChange={(event) =>
                          setEditing({ ...editing, parent_id: event.target.value })
                        }
                      >
                        <option value="">Kök seviye</option>
                        {flat
                          .filter(({ node: candidate }) => !blockedParents.has(candidate.id))
                          .map(({ node: candidate }) => (
                            <option key={candidate.id} value={candidate.id}>
                              {candidate.title}
                            </option>
                          ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>Önkoşullar</label>
                      <div className="checkbox-grid">
                        {prerequisiteChoices.map(({ node: candidate }) => (
                          <label key={candidate.id} className="checkbox-item">
                            <input
                              type="checkbox"
                              checked={editing.prerequisites.includes(candidate.id)}
                              onChange={() =>
                                setEditing({
                                  ...editing,
                                  prerequisites: toggle(editing.prerequisites, candidate.id),
                                })
                              }
                            />
                            {candidate.title}
                          </label>
                        ))}
                      </div>
                    </div>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setEditing(null)}
                        disabled={busy}
                      >
                        Vazgeç
                      </button>
                      <button className="btn btn-primary" disabled={busy}>
                        {busy ? "Kaydediliyor…" : "Kaydet"}
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default function AdminSkillsPage() {
  return (
    <Protected roles={["reviewer", "admin"]}>
      <SkillManager />
    </Protected>
  );
}
