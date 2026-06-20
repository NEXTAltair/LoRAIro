// ErrorsScreen — failure triage: summary, cross-filters, grouped error cards.
const DS_ERRORS = window.LoRAIroDesignSystem_64d8f7;

function ErrorsScreen() {
  const { Card, Button, Chip, TypeBadge, SummaryStat, SegmentedControl } = DS_ERRORS;
  const [status, setStatus] = React.useState("open");

  const operations = [["annotation", 19], ["registration", 6], ["processing", 7], ["thumbnail", 1], ["search", 0]];
  const terminal = [["FAILED", 31], ["CANCELED", 4], ["TERMINATED", 2], ["UNRESPONSIVE", 1]];

  const groups = [
    {
      type: "API", tone: "err", n: 12, code: "RATE_LIMITED",
      msg: "OpenAI rate limit exceeded (429)", model: "gpt-4o-caption", op: "annotation",
      images: 12, retryable: true, spark: [2, 4, 3, 6, 5, 8, 12],
    },
    {
      type: "Network", tone: "err", n: 5, code: "CONN_TIMEOUT",
      msg: "Connection timed out after 30s", model: "claude-3-5-sonnet", op: "annotation",
      images: 5, retryable: true, spark: [1, 0, 2, 1, 3, 2, 5],
    },
    {
      type: "IO", tone: "warn", n: 8, code: "FILE_NOT_FOUND",
      msg: "Source file missing — moved or deleted", model: "—", op: "registration",
      images: 8, retryable: false, spark: [3, 3, 2, 4, 1, 0, 8],
    },
    {
      type: "pHash", tone: "warn", n: 2, code: "DUPLICATE",
      msg: "Perceptual hash collision on import", model: "—", op: "registration",
      images: 2, retryable: false, spark: [0, 1, 0, 0, 1, 0, 2],
    },
  ];

  const Spark = ({ data }) => {
    const max = Math.max(...data, 1);
    return (
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 22 }}>
        {data.map((v, i) => (
          <div key={i} style={{ width: 4, height: Math.max(2, (v / max) * 22), background: i === data.length - 1 ? "var(--accent)" : "var(--line-strong)", borderRadius: 1 }} />
        ))}
      </div>
    );
  };

  const Facet = ({ items }) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
      {items.map(([nm, n]) => (
        <div key={nm} style={{ display: "flex", justifyContent: "space-between", padding: "3px 6px", borderRadius: "var(--radius)", fontSize: "var(--fs-small)", color: n === 0 ? "var(--ink-faint)" : "var(--ink)" }}>
          <span style={{ fontFamily: "var(--font-mono)" }}>{nm}</span>
          <span style={{ fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>{n}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>エラー — triage</h2>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--gap-3)" }}>
        <SummaryStat label="未解決 unresolved" value="33 件" sub="retry可 31 · 上限到達 2" tone="err" />
        <SummaryStat label="過去24時間 last 24h" value="18 件" sub="↑ +12 vs 前日" tone="warn" />
        <SummaryStat label="解決済 resolved (7d)" value="318 件" sub="auto-retry 284" tone="ok" />
        <SummaryStat label="error_type 別" value="API 18" sub="IO 8 · Net 5 · pHash 2" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "210px 1fr", gap: "var(--gap-3)", alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
          <Card title="operation">
            <Facet items={operations} />
          </Card>
          <Card title="終了状態 terminal">
            <Facet items={terminal} />
            <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)", marginTop: "var(--gap-2)" }}>
              superseded 4（非表示） — 置換された古い worker の失敗 (ADR 0034)
            </div>
          </Card>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", flexWrap: "wrap" }}>
            <SegmentedControl value={status} onChange={setStatus} options={[
              { value: "open", label: "未解決", count: 33 },
              { value: "resolved", label: "解決済", count: 318 },
              { value: "ignored", label: "無視", count: 3 },
              { value: "all", label: "すべて", count: 354 },
            ]} />
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>同一原因はまとめて表示 · grouped</span>
          </div>

          {groups.map((g, i) => (
            <Card key={i}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", marginBottom: 6 }}>
                <Chip kind={g.tone}>{g.type} {g.n}</Chip>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink)" }}>{g.code}</code>
                <TypeBadge>{g.op}</TypeBadge>
                {g.model !== "—" && <TypeBadge>{g.model}</TypeBadge>}
                <span style={{ flex: 1 }} />
                <Spark data={g.spark} />
              </div>
              <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", marginBottom: 8 }}>
                {g.msg} · 影響画像 {g.images} 枚
                <span style={{ color: "var(--accent)", cursor: "pointer", marginLeft: 6 }}>表示 →</span>
              </div>
              <div style={{ display: "flex", gap: "var(--gap-2)" }}>
                {g.retryable
                  ? <Button size="small" variant="primary">再実行 retry</Button>
                  : <Chip kind="muted" dot="open">上限到達 / retry不可</Chip>}
                <Button size="small">解決済にする</Button>
                <Button size="small" variant="ghost">無視</Button>
              </div>
            </Card>
          ))}

          <div style={{ display: "flex", gap: "var(--gap-2)", padding: "var(--gap-2)", borderTop: "1px solid var(--line)" }}>
            <Button size="small" variant="primary">retry可をすべて再実行 (31)</Button>
            <Button size="small">選択を無視</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

window.ErrorsScreen = ErrorsScreen;
