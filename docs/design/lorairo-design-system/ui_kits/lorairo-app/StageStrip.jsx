// StageStrip — shared staged-image thumbnail tray.
// Shown on Search / Annotate / Jobs / Results / Export so the current staging
// set is always visible as context. Mirrors the original Search stage tray.
const DS_STAGE = window.LoRAIroDesignSystem_64d8f7;

function StageStrip({ staged = 0, caption, action, title = "Stage", style }) {
  return (
    <div style={{ border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", background: "var(--card)", overflow: "hidden", ...style }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "7px 10px", borderBottom: "1px solid var(--line)", background: "var(--paper-shade)" }}>
        <span style={{ fontWeight: 700, fontSize: "var(--fs-small)" }}>{title}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--fs-small)", color: "var(--accent)", background: "var(--accent-soft)", borderRadius: "var(--radius-badge)", padding: "0 7px" }}>{staged}</span>
        {caption && <span style={{ flex: 1, minWidth: 0, fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{caption}</span>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "8px 10px" }}>
        <div style={{ flex: 1, display: "flex", gap: 6, overflowX: "auto", paddingBottom: 2 }}>
          {Array.from({ length: staged }).map((_, i) => (
            <div key={i} title={"img_" + String(i + 1).padStart(4, "0")} style={{ flex: "none", width: 44, height: 44, borderRadius: "var(--radius)", background: "linear-gradient(135deg, var(--paper-shade), #e6e2d5)", border: "1px solid var(--accent)" }} />
          ))}
          {staged === 0 && <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>ステージ済みの画像はありません — 検索タブで「選択をステージへ」</span>}
        </div>
        {action && <div style={{ flex: "none" }}>{action}</div>}
      </div>
    </div>
  );
}

window.StageStrip = StageStrip;
