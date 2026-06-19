// AnnotateScreen — pipeline stage strip + model picker + run card.
const DS_ANNOTATE = window.LoRAIroDesignSystem_64d8f7;

function AnnotateScreen({ staged, onRun }) {
  const { Card, Button, Chip, TypeBadge, StageCard, ModelRow } = DS_ANNOTATE;
  const [caption, setCaption] = React.useState("claude-haiku-4-5");

  const captionModels = [
    { name: "claude-haiku-4-5", badge: "anthropic", cost: "$0.0011/img · ~0.8s", chip: ["ok", "API ready"] },
    { name: "gemini-2.5-flash", badge: "google", cost: "$0.0007/img · ~0.6s", chip: ["ok", "API ready"] },
    { name: "gpt-5-mini", badge: "openai", cost: "$0.0009/img · ~0.7s", chip: ["warn", "needs key"] },
    { name: "moondream3", badge: "local", cost: "free · ~2.4s (GPU)", chip: ["ok", "installed"] },
    { name: "gpt-4-vision-preview", badge: "openai", cost: "—", chip: ["muted", "discontinued"], disabled: true },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", gap: "var(--gap-4)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
        <Card title="ステージ">
          <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            対象 {staged} 枚（検索から追加）
          </div>
          <div style={{ marginTop: "var(--gap-2)", display: "flex", gap: 6, flexWrap: "wrap" }}>
            <Chip kind="neutral" dot="open">未処理 96</Chip>
            <Chip kind="ok">済 32</Chip>
          </div>
          <div style={{ marginTop: "var(--gap-3)" }}>
            <Button size="small">ステージをクリア</Button>
          </div>
        </Card>
        <Card title="実行">
          <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            3 推論 / 枚 · 推定 $0.42 / 約 6 分
          </div>
          <div style={{ marginTop: 10 }}>
            <Button variant="primary" style={{ width: "100%", justifyContent: "center" }} onClick={onRun}>
              RUN PIPELINE ▶
            </Button>
          </div>
          <div style={{ marginTop: 6, fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            実行はジョブタブで追跡できます
          </div>
        </Card>
      </div>

      <div>
        <h2 style={{ margin: "0 0 var(--gap-2)", fontSize: "var(--fs-h2)", fontWeight: 700 }}>パイプライン構成</h2>
        <div style={{ display: "flex", alignItems: "stretch", gap: "var(--gap-2)", marginBottom: "var(--gap-3)" }}>
          <StageCard label="TAGGER" model="wd-eva02-large-v3" active status={<Chip kind="ok">installed</Chip>} />
          <span style={{ display: "flex", alignItems: "center", color: "var(--ink-faint)" }}>→</span>
          <StageCard label="CAPTION" model={caption} status={<Chip kind="ok">API ready</Chip>} />
          <span style={{ display: "flex", alignItems: "center", color: "var(--ink-faint)" }}>→</span>
          <StageCard label="SCORER" model="aesthetic-shadow-v2" status={<Chip kind="ok">installed</Chip>} />
        </div>

        <Card title="モデルピッカー — CAPTION ステージ" aside={<TypeBadge>multimodal</TypeBadge>}>
          {captionModels.map((m) => (
            <ModelRow
              key={m.name}
              status={<Chip kind={m.chip[0]}>{m.chip[1]}</Chip>}
              name={m.name}
              badge={<TypeBadge>{m.badge}</TypeBadge>}
              cost={m.cost}
              disabled={m.disabled}
              onClick={m.disabled ? undefined : () => setCaption(m.name)}
              style={m.name === caption ? { background: "var(--accent-soft)" } : undefined}
            />
          ))}
          <div style={{ marginTop: "var(--gap-2)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            ○ needs key をクリックすると設定の該当プロバイダ欄が開きます
          </div>
        </Card>
      </div>
    </div>
  );
}

window.AnnotateScreen = AnnotateScreen;
