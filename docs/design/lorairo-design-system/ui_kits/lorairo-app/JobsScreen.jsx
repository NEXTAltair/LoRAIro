// JobsScreen — summary strip, running pipeline (per-stage), queue + history.
const DS_JOBS = window.LoRAIroDesignSystem_64d8f7;

function JobsScreen({ running }) {
  const { Card, DataTable, Chip, TypeBadge, ProgressBar, SummaryStat, Button } = DS_JOBS;

  const stages = [
    { stage: "TAGS", model: "wd-v1-4-tagger", meta: "model_id 3 · local", pct: 100, done: "9 / 9", tone: "ok" },
    { stage: "TAGS", model: "wd-eva02-large", meta: "model_id 4 · local · GPU", pct: 67, done: "6 / 9 · 18s", tone: "info" },
    { stage: "CAPTION", model: "gpt-4o-caption", meta: "model_id 7 · OpenAI · MULTI ↝ +T +R", pct: 33, done: "⊙ レート待機 12s", tone: "info", striped: true },
    { stage: "SCORE", model: "aesthetic-v2", meta: "model_id 11 · local", pct: 100, done: "9 / 9", tone: "ok" },
    { stage: "RATING", model: "wd-rating-v2", meta: "model_id 10 · local", pct: 100, done: "9 / 9", tone: "ok" },
  ];

  const history = [
    { id: "h1", tone: "ok", state: "完了", kind: "annotation", body: "キャプション 96 枚 (claude-haiku-4-5)", result: "成功 96 / 失敗 0", time: "14:32" },
    { id: "h2", tone: "err", state: "失敗", kind: "provider_batch", body: "Batch 提出 512 枚 (gemini-2.5-flash)", result: "RATE_LIMITED — エラータブで詳細", time: "13:05" },
    { id: "h3", tone: "muted", dot: "open", state: "中止", kind: "db_register", body: "画像登録 2,400 枚", result: "処理済 1,180 で中断 · CANCELED", time: "11:48" },
    { id: "h4", tone: "ok", state: "完了", kind: "model_install", body: "wd-eva02-large-v3 install", result: "780.0 MB", time: "10:21" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>ジョブ</h2>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--gap-3)" }}>
        <SummaryStat label="実行中 running" value={running ? "1" : "0"} sub="既定パイプライン · staged 9" tone="info" />
        <SummaryStat label="待機 queued" value="2 件" sub="36 images · est. 8m" />
        <SummaryStat label="過去7日完了 done (7d)" value="17 件" sub="3,420 outputs · ✓ 14 · warn 3" tone="ok" />
        <SummaryStat label="API使用 (1m)" value="22 / 60" sub="OpenAI · auto-throttle" tone="warn" />
      </div>

      {running && (
        <Card title={<span>▶ 実行中 — 既定パイプライン · staged 9枚</span>}
          aside={<span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>00:42 / est 02:40 · job #J-1428</span>}>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {stages.map((s, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "70px 1fr 200px 96px", alignItems: "center", gap: "var(--gap-2)", padding: "5px 6px", borderRadius: "var(--radius)" }}>
                <span style={{ fontSize: "var(--fs-small)", fontWeight: 700, color: "var(--ink-soft)", letterSpacing: "var(--letter-caps)" }}>{s.stage}</span>
                <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {s.model} <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>· {s.meta}</span>
                </span>
                <ProgressBar value={s.pct} tone={s.tone === "ok" ? "ok" : "info"} striped={s.striped} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: s.tone === "ok" ? "var(--ok)" : "var(--ink-soft)", textAlign: "right" }}>{s.done}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", marginTop: "var(--gap-3)" }}>
            <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", flex: 1 }}>完了 4 / 6 ステージ · 41 / 54 outputs 書込済 · エラー 0 · 完了後そのまま Results へ</span>
            <Button size="small">一時停止</Button>
            <Button size="small">✕ キャンセル</Button>
          </div>
        </Card>
      )}

      <Card title="履歴">
        <DataTable
          columns={[
            { key: "state", header: "状態", width: "84px", render: (r) => <Chip kind={r.tone} dot={r.dot}>{r.state}</Chip> },
            { key: "kind", header: "種別", width: "130px", render: (r) => <TypeBadge>{r.kind}</TypeBadge> },
            { key: "body", header: "内容" },
            { key: "result", header: "結果", render: (r) => (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: r.tone === "err" ? "var(--err)" : "var(--ink-soft)" }}>{r.result}</span>
            ) },
            { key: "time", header: "完了", align: "right", width: "60px", render: (r) => (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{r.time}</span>
            ) },
          ]}
          rows={history}
        />
      </Card>
    </div>
  );
}

window.JobsScreen = JobsScreen;
