// MapScreen — keyword-driven co-occurrence tag explorer (NOT a scatter plot).
// Mirrors tag_cloud_widget.py: force-laid network graph + tag-cloud toggle,
// keyword search, drill-down chips. Node size = frequency, edge width = co-occ.
const DS_MAP = window.LoRAIroDesignSystem_64d8f7;

// frequency 0..1 → warm-grey (#9a9488) → accent (#c25e3f) ramp (theme _ramp_color)
function rampColor(t) {
  const e = Math.pow(Math.max(0, Math.min(1, t)), 0.85);
  const lo = [154, 148, 136], hi = [194, 94, 63];
  const c = (i) => Math.round(lo[i] + (hi[i] - lo[i]) * e);
  return `rgb(${c(0)},${c(1)},${c(2)})`;
}

const NODES = [
  { tag: "1girl", w: 1.0, x: 400, y: 250, count: 8420 },
  { tag: "solo", w: 0.8, x: 295, y: 175, count: 6210 },
  { tag: "long_hair", w: 0.65, x: 525, y: 175, count: 4980 },
  { tag: "looking_at_viewer", w: 0.55, x: 575, y: 300, count: 3640 },
  { tag: "smile", w: 0.6, x: 455, y: 365, count: 4120 },
  { tag: "outdoor", w: 0.7, x: 240, y: 330, count: 5180 },
  { tag: "cherry_blossom", w: 0.5, x: 165, y: 225, count: 2410 },
  { tag: "school_uniform", w: 0.45, x: 360, y: 110, count: 2050 },
  { tag: "blue_sky", w: 0.4, x: 140, y: 385, count: 1720 },
  { tag: "standing", w: 0.42, x: 325, y: 405, count: 1840 },
  { tag: "skirt", w: 0.38, x: 480, y: 435, count: 1510 },
  { tag: "day", w: 0.35, x: 110, y: 300, count: 1280 },
  { tag: "tree", w: 0.3, x: 225, y: 440, count: 980 },
  { tag: "short_sleeves", w: 0.28, x: 615, y: 200, count: 760 },
];
const IDX = Object.fromEntries(NODES.map((n, i) => [n.tag, i]));
const EDGES = [
  ["1girl", "solo", 0.9], ["1girl", "long_hair", 0.7], ["1girl", "smile", 0.8],
  ["1girl", "looking_at_viewer", 0.75], ["1girl", "outdoor", 0.6], ["1girl", "school_uniform", 0.5],
  ["1girl", "standing", 0.55], ["1girl", "skirt", 0.45], ["solo", "outdoor", 0.4],
  ["outdoor", "cherry_blossom", 0.6], ["outdoor", "blue_sky", 0.5], ["outdoor", "tree", 0.45],
  ["outdoor", "day", 0.5], ["cherry_blossom", "tree", 0.4], ["blue_sky", "day", 0.55],
  ["long_hair", "looking_at_viewer", 0.5], ["school_uniform", "skirt", 0.5],
  ["school_uniform", "short_sleeves", 0.35], ["smile", "looking_at_viewer", 0.4], ["standing", "skirt", 0.4],
].map(([a, b, norm]) => ({ a: IDX[a], b: IDX[b], norm }));

const ADJ = NODES.map(() => new Set());
EDGES.forEach((e) => { ADJ[e.a].add(e.b); ADJ[e.b].add(e.a); });

function MapScreen() {
  const { Card, Button, Input, SegmentedControl } = DS_MAP;
  const [view, setView] = React.useState("network");
  const [hover, setHover] = React.useState(-1);
  const [drill, setDrill] = React.useState(["1girl"]);
  const [tagLang, setTagLang] = React.useState("en"); // タグ表示言語（SearchScreen と共有の tagI18n）

  // 多言語表示は単一実装 tagI18n.jsx を共有。en = danbooru canonical（保存値）。表示のみ翻訳。
  const { LANGS, trTag: trTagAt, hasTr: hasTrAt } = window.LoRAIroTagI18n;
  const trTag = (t) => trTagAt(tagLang, t);
  const hasTr = (t) => hasTrAt(tagLang, t);

  const addDrill = (tag) => setDrill((d) => (d.includes(tag) ? d : [...d, tag]));
  const removeDrill = (tag) => setDrill((d) => d.filter((t) => t !== tag));

  const matched = 8420;
  const total = 12480;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      {/* top bar */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>マップ — 共起タグ探索</h2>
        <span style={{ flex: 1, minWidth: 120 }}>
          <Input placeholder="キーワードを入力（部分一致）して関連タグを探索…" defaultValue="1girl" style={{ fontSize: "var(--fs-small)" }} />
        </span>
        <SegmentedControl size="small" value={view} onChange={setView}
          options={[{ value: "network", label: "ネットワーク" }, { value: "cloud", label: "クラウド" }]} />
        <select value={tagLang} onChange={(ev) => setTagLang(ev.target.value)} title="表示言語 Translation" style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink)", background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", padding: "2px 4px", cursor: "pointer" }}>
          {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>
        <Button size="small">リセット</Button>
        <Button size="small" variant="ghost">↺ 再読込</Button>
      </div>

      {/* drill-down chips */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>ドリルダウン:</span>
        {drill.length === 0 ? (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)", border: "1px dashed var(--line-strong)", borderRadius: "var(--radius-chip)", padding: "2px 8px" }}>
            なし — ノードをクリックして絞り込み
          </span>
        ) : drill.map((t) => (
          <span key={t} title={tagLang === "en" ? t : t + " → " + trTag(t)} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", borderRadius: "var(--radius-chip)", padding: "1px 4px 1px 8px", fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--accent-hover)" }}>
            {trTag(t)}
            <button onClick={() => removeDrill(t)} style={{ border: "none", background: "transparent", color: "var(--accent-hover)", cursor: "pointer", fontSize: 11, padding: 0 }}>✕</button>
          </span>
        ))}
      </div>

      {/* status line */}
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
        該当 {matched.toLocaleString()}枚 / 全 {total.toLocaleString()}枚 · {NODES.length}タグ · 表示 {NODES.length}ノード / {EDGES.length}共起 · 絞り込み中
        {tagLang !== "en" && <span style={{ color: "var(--ink-faint)" }}> · 表示のみ翻訳（{tagLang}）· 保存値は danbooru canonical 固定</span>}
      </div>

      {/* stage */}
      <div style={{ position: "relative", background: "var(--card)", border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        {view === "network" ? (
          <React.Fragment>
            <svg viewBox="0 0 740 510" style={{ display: "block", width: "100%", aspectRatio: "740 / 510" }}>
              {EDGES.map((e, i) => {
                const lit = hover < 0 || hover === e.a || hover === e.b;
                const stroke = hover >= 0 && lit ? "rgba(194,94,63,.55)" : hover >= 0 ? "rgba(185,180,165,.12)" : "rgba(155,148,136," + (0.18 + e.norm * 0.4) + ")";
                return <line key={i} x1={NODES[e.a].x} y1={NODES[e.a].y} x2={NODES[e.b].x} y2={NODES[e.b].y}
                  stroke={stroke} strokeWidth={0.7 + e.norm * (hover >= 0 && lit ? 4 : 3.4)} strokeLinecap="round" />;
              })}
              {NODES.map((n, i) => {
                const r = 8 + 19 * Math.sqrt(n.w);
                const neighbor = hover >= 0 && (hover === i || ADJ[hover].has(i));
                const dim = hover >= 0 && !neighbor;
                return (
                  <g key={n.tag} style={{ cursor: "pointer", opacity: dim ? 0.28 : 1 }}
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(-1)} onClick={() => addDrill(n.tag)}>
                    <circle cx={n.x} cy={n.y} r={r} fill={rampColor(n.w)}
                      stroke={hover === i ? "#26241f" : "rgba(255,255,255,.75)"} strokeWidth={hover === i ? 2.5 : 1} />
                    <text x={n.x} y={n.y + r + 12 + n.w * 4} textAnchor="middle"
                      fontFamily="var(--font-mono)" fontSize={10 + 9 * n.w}
                      fontWeight={hover === i || n.w > 0.55 ? 600 : 400}
                      fill={hover === i ? "#26241f" : n.w > 0.55 ? "#3a342e" : "#76706a"}
                      stroke="rgba(255,255,255,.92)" strokeWidth="3" paintOrder="stroke">{trTag(n.tag)}</text>
                  </g>
                );
              })}
            </svg>
            {/* legend */}
            <div style={{ position: "absolute", left: 12, bottom: 12, background: "rgba(255,255,255,.92)", border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: "6px 10px", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>
              <div style={{ color: "var(--ink-faint)" }}>出現頻度  低 → 高</div>
              <div style={{ display: "flex", margin: "4px 0" }}>
                {[0, 0.25, 0.5, 0.75, 1].map((t) => <span key={t} style={{ width: 22, height: 9, background: rampColor(t) }} />)}
              </div>
              <div>線の太さ = 共起の強さ</div>
            </div>
            {/* hint */}
            <div style={{ position: "absolute", right: 12, top: 12, background: "rgba(255,255,255,.92)", border: "1px solid var(--line)", borderRadius: "var(--radius-chip)", padding: "3px 11px", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>
              ノードをクリックで絞り込み・ホバーで近傍を強調
            </div>
          </React.Fragment>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", alignItems: "center", padding: "var(--gap-4)", minHeight: 340 }}>
            {[...NODES].sort((a, b) => b.w - a.w).map((n) => (
              <span key={n.tag} onClick={() => addDrill(n.tag)} title={(tagLang === "en" ? n.tag : n.tag + " → " + trTag(n.tag)) + " · " + n.count.toLocaleString() + "枚 — クリックで絞り込み"}
                style={{ fontFamily: "var(--font-mono)", cursor: "pointer", lineHeight: 1.1,
                  fontSize: (13 + 34 * Math.pow(n.w, 0.8)) + "px",
                  fontWeight: n.w > 0.55 ? 600 : 400, color: rampColor(n.w) }}>
                {trTag(n.tag)}
              </span>
            ))}
          </div>
        )}
      </div>

      <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>
        探索専用 — タグ（ノード）クリックで AND 絞り込み。配置= タグ頻度ベクトル(cosine)→2D · クラスタ= Jaccard 共起グラフ。embedding ではなく既存 Tag テーブルのみで成立。
      </div>
    </div>
  );
}

window.MapScreen = MapScreen;
