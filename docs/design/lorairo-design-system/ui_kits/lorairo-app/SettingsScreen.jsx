// SettingsScreen — ConfigurationWindow modal: API keys, model route, installer.
const DS_SETTINGS = window.LoRAIroDesignSystem_64d8f7;

function SettingsScreen({ onClose }) {
  const { Button, Chip, TypeBadge, SegmentedControl } = DS_SETTINGS;
  const [route, setRoute] = React.useState("auto");

  const keys = [
    { name: "OpenAI", tone: "ok", txt: "保存済み saved", masked: true },
    { name: "Anthropic", tone: "ok", txt: "保存済み saved", masked: true },
    { name: "Google", tone: "warn", txt: "未設定 not set", masked: false, highlight: true },
  ];
  const models = [
    { name: "wd-eva02-large-v3", size: "0.78 GB", installed: true },
    { name: "aesthetic-shadow-v2", size: "1.20 GB", installed: true },
    { name: "moondream3", size: "3.40 GB", installed: false },
  ];

  const Section = ({ title, sub, children }) => (
    <div style={{ padding: "var(--gap-3) 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-2)", marginBottom: "var(--gap-2)" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-base)", fontWeight: 600 }}>{title}</h3>
        {sub && <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>{sub}</code>}
      </div>
      {children}
    </div>
  );

  return (
    <div style={{
      position: "fixed", inset: 0, background: "var(--scrim)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 560, maxWidth: "92vw", maxHeight: "88vh", overflow: "auto",
        background: "var(--card)", border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-shell)", boxShadow: "var(--shadow-shell)",
      }}>
        <div style={{ display: "flex", alignItems: "center", padding: "12px 16px", background: "var(--paper-shade)", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontWeight: 600 }}>⚙ 設定 Settings</span>
          <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", marginLeft: 8 }}>config/lorairo.toml</code>
          <span style={{ flex: 1 }} />
          <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, color: "var(--ink-soft)" }}>✕</button>
        </div>

        <div style={{ padding: "4px 16px 16px" }}>
          <Section title="API キー keys" sub="[api]">
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {keys.map((k) => (
                <div key={k.name} style={{
                  display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "6px 8px", borderRadius: "var(--radius)",
                  background: k.highlight ? "var(--accent-soft)" : "transparent",
                  border: "1px solid " + (k.highlight ? "var(--accent-border)" : "transparent"),
                }}>
                  <span style={{ width: 84 }}>{k.name}</span>
                  <Chip kind={k.tone}>{k.txt}</Chip>
                  {k.masked ? (
                    <React.Fragment>
                      <span style={{ flex: 1, fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>••••••••••••••••</span>
                      <Button size="small">上書き replace</Button>
                    </React.Fragment>
                  ) : (
                    <React.Fragment>
                      <input placeholder="キーを貼り付け…（入力中もマスク）" style={{
                        flex: 1, boxSizing: "border-box", padding: "4px 8px", fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)",
                        border: "1px solid var(--accent)", borderRadius: "var(--radius)", outline: "none", background: "var(--card)",
                      }} />
                      <Button size="small" variant="primary">保存 save</Button>
                    </React.Fragment>
                  )}
                </div>
              ))}
            </div>
            <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)", marginTop: "var(--gap-2)" }}>
              平文表示なし・表示切替なし。分かるのは「保存済みかどうか」だけ。
            </div>
          </Section>

          <Section title="モデル経路 model route" sub="route_preference">
            <SegmentedControl value={route} onChange={setRoute} options={["auto", "direct", "openrouter"]} />
            <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", marginTop: "var(--gap-2)" }}>
              auto: キー状況に応じ direct 優先。「all」は CLI 専用（--route all）· GUI は3値のみ (Issue #249)
            </div>
          </Section>

          <Section title="モデルインストーラ installer" sub="estimated_size_gb">
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              {models.map((m) => (
                <div key={m.name} style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "5px 6px" }}>
                  {m.installed ? <Chip kind="ok">installed</Chip> : <Chip kind="neutral" dot="open">未install</Chip>}
                  <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.name}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{m.size}</span>
                  <Button size="small">{m.installed ? "削除 uninstall" : "install"}</Button>
                </div>
              ))}
            </div>
            <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)", marginTop: "var(--gap-2)" }}>
              合計 1.98 GB installed · install は Jobs に同居（中止 = CANCELED）
            </div>
          </Section>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--gap-2)", paddingTop: "var(--gap-3)" }}>
            <Button onClick={onClose}>閉じる</Button>
            <Button variant="primary" onClick={onClose}>保存</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

window.SettingsScreen = SettingsScreen;
