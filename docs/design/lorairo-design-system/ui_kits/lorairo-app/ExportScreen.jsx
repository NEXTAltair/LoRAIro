// ExportScreen — build a training set from the staging set.
const DSX = window.LoRAIroDesignSystem_64d8f7;

function ExportScreen({ staged }) {
  const { Card, Button, Chip, TypeBadge, SummaryStat, SegmentedControl, Terminal } = DSX;
  const [fmt, setFmt] = React.useState("danbooru");
  const T = Terminal;

  const files = [
    { ext: ".txt", what: "tags", src: "Tag.tag" },
    { ext: ".caption", what: "caption", src: "Caption.text" },
    { ext: ".json", what: "metadata", src: "quality / score / rating" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-4)" }}>
      <window.StageStrip staged={staged} caption="エクスポート対象 = ステージング集合（明示・有界 MAX 500）" />
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: "var(--gap-4)", alignItems: "start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
        <SummaryStat label="エクスポート対象 export target" value="9 枚" sub="staging set · MAX 500" tone="accent" />
        <Card title="対象 = ステージング集合">
          <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", lineHeight: 1.7 }}>
            明示・有界（MAX 500）・可視・名前付き。「選択中」ではなくステージング件数を読む。全件出力は構造的に不可（ADR 0019）。
          </div>
          <div style={{ marginTop: "var(--gap-2)", display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>入口:</span>
            <Chip kind="neutral" dot="none">← Search</Chip>
            <Chip kind="neutral" dot="none">← Results</Chip>
          </div>
        </Card>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>エクスポート — 学習データセット書き出し</h2>

        <Card title="出力フォーマット output format">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-3)", flexWrap: "wrap" }}>
            <SegmentedControl value={fmt} onChange={setFmt}
              options={[{ value: "danbooru", label: "danbooru" }, { value: "e621", label: "e621" }, { value: "pony", label: "pony" }]} />
            <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>ターゲット別のタグ規則・エイリアス変換を適用</span>
          </div>
        </Card>

        <Card title={<span>出力ファイル output files <span style={{ fontWeight: 400, color: "var(--ink-soft)", fontSize: "var(--fs-small)" }}>常に 3 種 / 画像</span></span>}>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {files.map((f) => (
              <div key={f.ext} style={{ display: "grid", gridTemplateColumns: "160px 110px 1fr", alignItems: "center", gap: "var(--gap-2)", padding: "6px" }}>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink)" }}>{"{name}"}{f.ext}</code>
                <span style={{ fontSize: "var(--fs-small)" }}>{f.what}</span>
                <TypeBadge>{f.src}</TypeBadge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="変換プレビュー preview" aside={<TypeBadge>img_0001.txt</TypeBadge>}>
          <Terminal>
            <T.Muted># {fmt} format · img_0001.txt</T.Muted>{"\n"}
            {fmt === "e621"
              ? "1girl, outdoors, solo, smile, cherry_blossom"
              : fmt === "pony"
              ? "source_anime, 1girl, outdoors, solo, smile, score_9"
              : "1girl, outdoor, solo, smile, cherry blossoms"}
          </Terminal>
        </Card>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--gap-2)" }}>
          <Button>出力先を選択…</Button>
          <Button variant="primary">9 枚をエクスポート ▶</Button>
        </div>
      </div>
      </div>
    </div>
  );
}

window.ExportScreen = ExportScreen;
