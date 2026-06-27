// ResultsScreen — annotation quality triage for a finished batch.
const DS_RESULTS = window.LoRAIroDesignSystem_64d8f7;

function ResultsScreen({ staged }) {
  const { Card, Button, Chip, TypeBadge, TagChip, Thumbnail, SummaryStat, Terminal } = DS_RESULTS;

  const dist = [
    { band: "8–10", n: 3, pct: 33 },
    { band: "6–8", n: 4, pct: 44 },
    { band: "4–6", n: 1, pct: 11 },
    { band: "2–4", n: 1, pct: 11 },
  ];

  const issues = [
    { kind: "err", label: "空タグ empty tags", n: 1, hint: "img_0007 — TAGS が 0 件" },
    { kind: "warn", label: "rating 不一致 mismatch", n: 1, hint: "wd-rater R / gpt-4o PG-13" },
    { kind: "warn", label: "scorer 不一致", n: 1, hint: "aesthetic 0.9 / musiq 0.4" },
  ];

  const rows = [
    { id: "img_0001", dims: "1024×1536", flagged: false, tags: ["1girl", "outdoor", "solo", "smile"], cap: "a girl smiling under cherry blossoms", score: 0.82, rating: "PG-13" },
    { id: "img_0007", dims: "640×960", flagged: true, issue: "空タグ", tags: [], cap: "(no caption)", score: 0.45, rating: "—" },
    { id: "img_0003", dims: "1024×1024", flagged: false, tags: ["1girl", "indoor", "book"], cap: "a girl reading by the window", score: 0.91, rating: "PG" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-3)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>結果 — 品質トリアージ</h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
          batch #J-0418 · done 04-25 14:32 · 9枚 · 3モデル · 4ステージ
        </span>
        <span style={{ flex: 1 }} />
        <Button size="small" variant="ghost">↩ Jobs で見る</Button>
      </div>

      <window.StageStrip staged={staged} caption="このバッチ #J-0418 の対象集合 · staged.image_id" />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--gap-3)" }}>
        <SummaryStat label="バッチ枚数 batch size" value="9 枚" />
        <SummaryStat label="フラグあり flagged" value="3 枚" tone="warn" />
        <SummaryStat label="フラグなし clean" value="5 枚" tone="ok" />
        <SummaryStat label="保存済 saved" value="9 枚" sub="全結果を保存（非破壊）" tone="ok" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: "var(--gap-3)", alignItems: "start" }}>
        <Card title="品質スコア分布 quality_score">
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {dist.map((d) => (
              <div key={d.band} style={{ display: "grid", gridTemplateColumns: "44px 1fr 20px", alignItems: "center", gap: "var(--gap-2)" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{d.band}</span>
                <div style={{ height: 14, background: "var(--paper-shade)", borderRadius: "var(--radius-badge)", overflow: "hidden" }}>
                  <div style={{ width: d.pct + "%", height: "100%", background: "var(--accent)" }} />
                </div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", textAlign: "right" }}>{d.n}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title={<span>品質問題 — 構造的のみ <span style={{ fontWeight: 400, color: "var(--ink-soft)", fontSize: "var(--fs-small)" }}>structural issues only</span></span>}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}>
            {issues.map((iss, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "6px 8px", border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
                <Chip kind={iss.kind}>{iss.label}</Chip>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", flex: 1 }}>{iss.hint}</span>
                <Button size="small">▸ レビュー</Button>
              </div>
            ))}
            <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
              低信頼度タグ・短いキャプションは issue 化しない（行に表示済 · 目で足りる）
            </div>
          </div>
        </Card>
      </div>

      <Card title="画像単位の要約 image summary"
        aside={<span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>全結果は保存済（非破壊）· 品質レビュー（編集）のみ</span>}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}>
          {rows.map((r) => (
            <div key={r.id} style={{
              display: "grid", gridTemplateColumns: "72px 1fr auto", gap: "var(--gap-3)", alignItems: "center",
              padding: "var(--gap-2)", border: "1px solid " + (r.flagged ? "var(--warn-border)" : "var(--line)"),
              background: r.flagged ? "var(--warn-soft)" : "var(--card)", borderRadius: "var(--radius)",
            }}>
              <div style={{ width: 72 }}>
                <Thumbnail label={r.id} dims={r.dims} score={r.score} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", marginBottom: 4 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{r.id}</span>
                  {r.flagged
                    ? <Chip kind="err">{r.issue}</Chip>
                    : <Chip kind="ok">clean</Chip>}
                  <TypeBadge>rating {r.rating}</TypeBadge>
                  <TypeBadge>score {r.score}</TypeBadge>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3, marginBottom: 3 }}>
                  {r.tags.length ? r.tags.map((t) => <TagChip key={t}>{t}</TagChip>)
                    : <span style={{ fontSize: "var(--fs-small)", color: "var(--err)" }}>タグなし</span>}
                </div>
                <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>“{r.cap}”</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                {r.flagged && <Button size="small" variant="primary">▸ レビュー</Button>}
                <Button size="small">編集</Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

window.ResultsScreen = ResultsScreen;
