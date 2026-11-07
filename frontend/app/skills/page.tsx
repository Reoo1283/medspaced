"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import Protected from "@/components/Protected";
import { Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { SkillNode } from "@/lib/types";

interface FlatSkill {
  node: SkillNode;
  depth: number;
}

function flatten(nodes: SkillNode[], depth = 0): FlatSkill[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...flatten(node.children ?? [], depth + 1),
  ]);
}

function SkillsScreen() {
  const [tree, setTree] = useState<SkillNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setTree(null);
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

  const unlockedCount = flat.filter(({ node }) => node.unlocked).length;
  const masteredCount = flat.filter(({ node }) => node.mastery_score >= 70).length;

  return (
    <>
      <PageHeader
        title="Yetenek ağacı"
        description="Önkoşulları tamamlayarak yeni konuların kilidini açın."
        actions={
          <button className="btn btn-ghost" onClick={load} disabled={tree === null}>
            Yenile
          </button>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}
      {tree === null ? (
        <div className="card muted">Yetenekler yükleniyor…</div>
      ) : flat.length === 0 ? (
        <div className="card">
          <Empty>Henüz yetenek tanımlanmamış. Eğitmeniniz içerik eklediğinde burada görünecek.</Empty>
        </div>
      ) : (
        <>
          <div className="row" style={{ marginBottom: 18 }}>
            <span className="badge badge-approved">{unlockedCount} açık</span>
            <span className="badge">{flat.length} toplam</span>
            <span className="badge badge-under_review">{masteredCount} ustalaşıldı</span>
          </div>
          <div className="grid grid-3">
            {flat.map(({ node, depth }) => (
              <div
                className="card"
                key={node.id}
                style={{
                  marginLeft: depth * 8,
                  opacity: node.unlocked ? 1 : 0.6,
                }}
              >
                <div className="section-title">
                  <span className="badge">{node.category}</span>
                  {node.unlocked ? (
                    <span className="badge badge-approved">açık</span>
                  ) : (
                    <span className="badge badge-draft">kilitli</span>
                  )}
                </div>
                <h3>{node.title}</h3>
                {node.description ? (
                  <p className="muted small" style={{ marginTop: 0 }}>
                    {node.description}
                  </p>
                ) : null}
                <div className="meter" style={{ margin: "14px 0 8px" }}>
                  <span style={{ width: `${Math.min(100, node.mastery_score)}%` }} />
                </div>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="muted small">Hakimiyet: {node.mastery_score.toFixed(0)}%</span>
                  <span className="muted small">Eşik: 70%</span>
                </div>
                {node.prerequisites.length > 0 ? (
                  <p className="muted small" style={{ marginBottom: 0, marginTop: 12 }}>
                    Önkoşul:{" "}
                    {node.prerequisites
                      .map((id) => titles.get(id) ?? id)
                      .join(", ")}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export default function SkillsPage() {
  return (
    <Protected>
      <SkillsScreen />
    </Protected>
  );
}
