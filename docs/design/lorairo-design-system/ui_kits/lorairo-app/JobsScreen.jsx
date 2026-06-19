// JobsScreen — running/queue table, history table, CLI terminal pane.
const DS_JOBS = window.LoRAIroDesignSystem_64d8f7;

function JobsScreen({ running }) {
  const { Card, DataTable, Chip, TypeBadge, ProgressBar, Terminal } = DS_JOBS;
  const T = Terminal;

  const active = [
    running && {
      id: "j1", tone: "info", state: "実行中", kind: "annotation",
      body: "タグ付け 128 枚 × 3 モデル", pct: 32, meta: "32% (41/128)",
    },
    {
      id: "j2", tone: "info", state: "実行中", kind: "model_install",
      body: "wd-eva02-large-v3 をダウンロード中", pct: 45, meta: "45% (350.0/780.0 MB)",
    },
    {
      id: "j3", tone: "neutral", dot: "open", state: "待機", kind: "provider_batch",
      body: "Batch 提出 512 枚 (gemini-2.5-flash)", pct: 0, striped: true, meta: "rate 待機",
    },
  ].filter(Boolean);

  const history = [
    { id: "h1", tone: "ok", state: "完了", kind: "annotation", body: "キャプション 96 枚 (claude-haiku-4-5)", result: "成功 96 / 失敗 0", time: "14:32" },
    { id: "h2", tone: "err", state: "失敗", kind: "provider_batch", body: "Batch 提出 512 枚 (gemini-2.5-flash)", result: "RATE_LIMITED — エラータブで詳細", time: "13:05" },
    { id: "h3", tone: "muted", dot: "open", state: "中止", kind: "db_register", body: "画像登録 2,400 枚", result: "処理済 1,180 で中断", time: "11:48" },
  ];

  const stateCol = { key: "state", header: "状態", width: "84px",
    render: (r) => <Chip kind={r.tone} dot={r.dot}>{r.state}</Chip> };
  const kindCol = { key: "kind", header: "種別", width: "120px",
    render: (r) => <TypeBadge>{r.kind}</TypeBadge> };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>ジョブ</h2>
      <Card title="実行中 / キュー">
        <DataTable
          columns={[
            stateCol, kindCol,
            { key: "body", header: "内容" },
            { key: "prog", header: "進捗", width: "240px", render: (r) => (
              <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)" }}>
                <ProgressBar value={r.pct} striped={r.striped} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", whiteSpace: "nowrap" }}>{r.meta}</span>
              </div>
            ) },
          ]}
          rows={active}
        />
      </Card>
      <Card title="履歴">
        <DataTable
          columns={[
            stateCol, kindCol,
            { key: "body", header: "内容" },
            { key: "result", header: "結果", render: (r) => (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: r.tone === "err" ? "var(--err)" : "var(--ink-soft)" }}>{r.result}</span>
            ) },
            { key: "time", header: "完了", align: "right", width: "64px",
              render: (r) => <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{r.time}</span> },
          ]}
          rows={history}
        />
      </Card>
      <Card title="CLI ペイン例（参考: ダークペイン token）">
        <Terminal>
          <T.Muted>$ lorairo-cli annotate run --models wd-eva02 --json</T.Muted>{"\n"}
          {"{"}<T.K>"kind"</T.K>:<T.S>"item"</T.S>,<T.K>"image_id"</T.K>:<T.N>42</T.N>,<T.K>"tags"</T.K>:[<T.S>"1girl"</T.S>,<T.S>"outdoor"</T.S>]{"}"}{"\n"}
          {"{"}<T.K>"kind"</T.K>:<T.S>"result"</T.S>,<T.K>"count"</T.K>:<T.N>128</T.N>,<T.K>"has_more"</T.K>:<T.B>false</T.B>{"}"}
        </Terminal>
      </Card>
    </div>
  );
}

window.JobsScreen = JobsScreen;
