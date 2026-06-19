// AppShell — window titlebar (wordmark + project + gear) and the top nav tab bar.
// Reads DS components at module load from the compiled bundle namespace.
const DS = window.LoRAIroDesignSystem_64d8f7;

function AppShell({ tab, onTab, onGear, children }) {
  const { Tabs } = DS;
  const tabs = [
    { id: "search", label: "検索" },
    { id: "map", label: "マップ" },
    { id: "annotate", label: "アノテーション" },
    { id: "jobs", label: "ジョブ" },
    { id: "results", label: "結果" },
    { id: "errors", label: "エラー" },
    { id: "export", label: "エクスポート" },
    { id: "cli", label: "CLI" },
  ];
  return (
    <div style={{
      maxWidth: 1180, margin: "0 auto",
      border: "1px solid var(--line-strong)", borderRadius: "var(--radius-shell)",
      background: "var(--paper)", overflow: "hidden", boxShadow: "var(--shadow-shell)",
    }}>
      {/* titlebar */}
      <div style={{
        display: "flex", alignItems: "center", gap: "var(--gap-3)",
        padding: "8px 14px", background: "var(--paper-shade)", borderBottom: "1px solid var(--line)",
      }}>
        <div style={{ fontWeight: 700, fontSize: "var(--fs-h2)", letterSpacing: ".02em" }}>
          LoRA<span style={{ color: "var(--accent)" }}>Iro</span>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
          project: main_dataset_20260601_001
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={onGear} title="設定" style={{
          width: 28, height: 28, border: "1px solid var(--line)", borderRadius: "var(--radius)",
          background: "var(--card)", cursor: "pointer", color: "var(--ink-soft)", fontSize: 14,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>⚙</button>
      </div>
      {/* nav */}
      <Tabs tabs={tabs} active={tab} onChange={onTab} />
      {/* screen body */}
      <div style={{ padding: "var(--gap-4)" }}>{children}</div>
    </div>
  );
}

window.AppShell = AppShell;
