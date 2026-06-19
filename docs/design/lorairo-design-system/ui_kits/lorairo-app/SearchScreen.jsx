// SearchScreen — filter sidebar + NLQ + thumbnail results grid.
const DS_SEARCH = window.LoRAIroDesignSystem_64d8f7;

function SearchScreen({ staged, onStage }) {
  const { Card, Input, Select, Button, TagChip, Thumbnail } = DS_SEARCH;
  const [tags, setTags] = React.useState(["1girl", "outdoor", "solo"]);
  const [sel, setSel] = React.useState("img_0001");

  const images = [
    { id: "img_0001", dims: "1024×1536", score: 0.82 },
    { id: "img_0002", dims: "832×1216", score: 0.74 },
    { id: "img_0003", dims: "1024×1024", score: 0.91 },
    { id: "img_0004", dims: "1216×832", score: 0.66 },
    { id: "img_0005", dims: "1024×1536", score: 0.88 },
    { id: "img_0006", dims: "1024×1536", score: 0.79 },
    { id: "img_0007", dims: "640×960", score: 0.45 },
    { id: "img_0008", dims: "1024×1024", score: 0.93 },
    { id: "img_0009", dims: "896×1152", score: 0.71 },
    { id: "img_0010", dims: "1024×1536", score: 0.84 },
    { id: "img_0011", dims: "768×1024", score: 0.58 },
    { id: "img_0012", dims: "1152×896", score: 0.77 },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", gap: "var(--gap-4)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
        <Card title="フィルタ">
          <Input label="タグ検索" placeholder="1girl, solo, ..." />
          <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
            {tags.map((t) => (
              <TagChip key={t} onRemove={() => setTags(tags.filter((x) => x !== t))}>{t}</TagChip>
            ))}
          </div>
          <div style={{ marginTop: "var(--gap-2)" }}>
            <Select label="解像度" options={["すべて", "1024px 以上"]} />
          </div>
          <div style={{ marginTop: "var(--gap-2)" }}>
            <Select label="レーティング" options={["すべて", "PG", "PG-13", "R"]} />
          </div>
          <div style={{ marginTop: "var(--gap-2)" }}>
            <Input label="スコア" placeholder="0.6 以上" />
          </div>
          <div style={{ marginTop: "var(--gap-3)", display: "flex", gap: "var(--gap-2)" }}>
            <Button variant="primary">検索</Button>
            <Button>クリア</Button>
          </div>
        </Card>
        <Card title="NLQ">
          <Input placeholder="屋外で笑っている1人の女の子" />
          <div style={{ marginTop: 6, fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            自然文 → フィルタ変換
          </div>
        </Card>
      </div>

      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-3)", marginBottom: 10 }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>検索結果</h2>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
            1,247 件 / 表示 1–48
          </span>
          <span style={{ flex: 1 }} />
          <Button size="small" onClick={() => onStage(sel)}>選択をステージへ</Button>
          <Button size="small" variant="ghost">サムネイル ▾</Button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(124px,1fr))", gap: "var(--gap-3)" }}>
          {images.map((im) => (
            <Thumbnail
              key={im.id} label={im.id} dims={im.dims} score={im.score}
              selected={sel === im.id} onClick={() => setSel(im.id)}
            />
          ))}
        </div>
        <div style={{ marginTop: "var(--gap-3)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
          ステージング集合: {staged} 枚
        </div>
      </div>
    </div>
  );
}

window.SearchScreen = SearchScreen;
