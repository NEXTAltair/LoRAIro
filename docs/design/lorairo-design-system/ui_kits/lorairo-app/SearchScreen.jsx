// SearchScreen — full filter sidebar (registration summary, query, quality,
// rating by source, annotations state, model, date, errors)
// + results grid. Follows Wireframes v12 · Frame 1 · Search.
const DS_SEARCH = window.LoRAIroDesignSystem_64d8f7;

function SearchScreen({ staged, onStage }) {
  const { Card, Input, Button, Chip, TagChip, Thumbnail, SegmentedControl, ProgressBar } = DS_SEARCH;

  const [regOpen, setRegOpen] = React.useState(true);
  const [showSkips, setShowSkips] = React.useState(false);
  const [noScore, setNoScore] = React.useState("exclude");
  const [ratingCombine, setRatingCombine] = React.useState("AND");
  const [aiSel, setAiSel] = React.useState(["PG-13"]);
  const [manualSel, setManualSel] = React.useState([]);
  const toggleIn = (setFn) => (v) => setFn((cur) => cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
  const [errState, setErrState] = React.useState("all");
  const [showMoreModels, setShowMoreModels] = React.useState(false);
  const [sel, setSel] = React.useState("img_0001");
  // 品質スコア・日付は現リポジトリ同様に「範囲選択」（上下限）
  const [qRange, setQRange] = React.useState([6, 10]); // quality_score 下限・上限
  const DAYS = 30; // 履歴の取得期間（日）= スライダの全幅
  const [dateRange, setDateRange] = React.useState([0, DAYS]); // 何日前〜何日前
  const dayLabel = (back) => { const d = new Date("2025-04-25T00:00:00"); d.setDate(d.getDate() - (DAYS - back)); return d.toISOString().slice(0, 10); };
  // お気に入りの検索条件
  const [savedQueries, setSavedQueries] = React.useState([
    { name: "高品質 PG-13", sub: "q≥7 · PG-13 · 30d" },
    { name: "手動編集済", sub: "edited · 全期間" },
  ]);
  const [savedActive, setSavedActive] = React.useState(0);
  const saveCurrentQuery = () => {
    const sub = "q≥" + qRange[0].toFixed(1) + " · " + (aiSel.join("/") || "all") + " · " + (DAYS - dateRange[0]) + "d";
    setSavedActive(savedQueries.length);
    setSavedQueries((qs) => [...qs, { name: "検索 " + (qs.length + 1), sub }]);
  };

  // ---- small inline building blocks (screen-specific composition) ----
  const Group = ({ label, sub, children }) => (
    <div style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: "var(--fs-small)", fontWeight: 700, color: "var(--ink)", letterSpacing: "var(--letter-caps)", textTransform: "uppercase" }}>{label}</span>
        {sub && <code style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>{sub}</code>}
      </div>
      {children}
    </div>
  );
  const Facet = ({ label, count, checked, type = "check", onToggle, dim, strong }) => (
    <div onClick={onToggle} style={{
      display: "flex", alignItems: "center", gap: 7, padding: "3px 4px", borderRadius: "var(--radius)",
      cursor: onToggle ? "pointer" : "default", fontSize: "var(--fs-small)",
      color: dim ? "var(--ink-faint)" : "var(--ink)",
    }}>
      <span style={{
        width: 13, height: 13, flex: "none",
        border: "1px solid " + (checked ? "var(--accent)" : "var(--line-strong)"),
        borderRadius: type === "radio" ? "50%" : "3px",
        background: checked ? "var(--accent)" : "var(--card)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        color: "#fff", fontSize: 9,
      }}>{checked ? (type === "radio" ? "●" : "✓") : ""}</span>
      <span style={{ flex: 1, fontWeight: strong ? 600 : 400, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      {count != null && <span style={{ fontFamily: "var(--font-mono)", color: "var(--ink-soft)", fontSize: "10px" }}>{count}</span>}
    </div>
  );

  // multi-select rating chip (toggleable pill — clearer than a checkbox column)
  const RatingChip = ({ label, count, on, onClick, dim }) => (
    <button type="button" onClick={onClick} title={label + " · " + count.toLocaleString()} style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 8px", borderRadius: "var(--radius-chip)", cursor: "pointer",
      fontFamily: "var(--font-sans)", fontSize: "var(--fs-small)", lineHeight: 1.2,
      border: "1px solid " + (on ? "var(--accent)" : "var(--line-strong)"),
      background: on ? "var(--accent-soft)" : "var(--card)",
      color: on ? "var(--accent-hover)" : (dim ? "var(--ink-faint)" : "var(--ink)"),
      fontWeight: on ? 600 : 400,
    }}>
      <span>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: on ? "var(--accent-hover)" : "var(--ink-faint)" }}>{count.toLocaleString()}</span>
    </button>
  );

  // 二連ハンドルの範囲スライダ（現リポジトリの min–max 選択と同等）
  const RangeSlider = ({ min, max, step, value, onChange, format }) => {
    const [lo, hi] = value;
    const pct = (v) => ((v - min) / (max - min)) * 100;
    const fmt = format || ((v) => v);
    const base = { position: "absolute", top: 0, left: 0, width: "100%", height: 22, margin: 0, background: "transparent", pointerEvents: "none", accentColor: "var(--accent)" };
    return (
      <div style={{ padding: "0 2px" }}>
        <style>{".ds-range{-webkit-appearance:none;appearance:none}.ds-range::-webkit-slider-thumb{-webkit-appearance:none;pointer-events:auto;width:14px;height:14px;border-radius:50%;background:var(--accent);border:2px solid var(--card);box-shadow:0 0 0 1px var(--accent);cursor:pointer}.ds-range::-moz-range-thumb{pointer-events:auto;width:14px;height:14px;border-radius:50%;background:var(--accent);border:2px solid var(--card);cursor:pointer}.ds-range::-webkit-slider-runnable-track{background:transparent}.ds-range::-moz-range-track{background:transparent}"}</style>
        <div style={{ position: "relative", height: 22 }}>
          <div style={{ position: "absolute", top: 9, left: 0, right: 0, height: 4, borderRadius: 2, background: "var(--paper-shade)" }} />
          <div style={{ position: "absolute", top: 9, height: 4, borderRadius: 2, background: "var(--accent)", left: pct(lo) + "%", width: (pct(hi) - pct(lo)) + "%" }} />
          <input type="range" className="ds-range" min={min} max={max} step={step} value={lo}
            onChange={(e) => { const v = Math.min(parseFloat(e.target.value), hi); onChange([v, hi]); }} style={base} />
          <input type="range" className="ds-range" min={min} max={max} step={step} value={hi}
            onChange={(e) => { const v = Math.max(parseFloat(e.target.value), lo); onChange([lo, v]); }} style={base} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", marginTop: 2 }}>
          <span>{fmt(lo)}</span>
          <span>{fmt(hi)}</span>
        </div>
      </div>
    );
  };

  const [facets, setFacets] = React.useState({ tags: true, caption: false, fromText: true, edited: false });
  const tgl = (k) => setFacets((f) => ({ ...f, [k]: !f[k] }));

  // deterministic date histogram bars
  const bars = [];
  let s = 11;
  for (let i = 0; i < 22; i++) { s = (s * 9301 + 49297) % 233280; bars.push(0.25 + (s / 233280) * 0.75); }

  const aiRatings = [["PG", 3210], ["PG-13", 5840], ["R", 2140], ["X", 820], ["XXX", 120], ["未設定 unset", 1180]];
  const manualRatings = [["PG", 240], ["PG-13", 180], ["R", 160], ["X", 70], ["XXX", 18], ["なし none", 11812]];

  const images = [
    { id: "img_0001", dims: "2048×3072", score: 0.93, rating: "PG" },
    { id: "img_0002", dims: "1536×2048", score: 0.91, rating: "PG-13" },
    { id: "img_0003", dims: "1024×1536", score: 0.88, rating: "PG-13" },
    { id: "img_0004", dims: "2048×2048", score: 0.86, rating: "PG" },
    { id: "img_0005", dims: "1280×1920", score: 0.84, rating: "PG-13" },
    { id: "img_0006", dims: "1024×1024", score: 0.82, rating: "PG" },
    { id: "img_0007", dims: "1536×2048", score: 0.81, rating: "R" },
    { id: "img_0008", dims: "1024×1536", score: 0.79, rating: "PG-13" },
    { id: "img_0009", dims: "1024×1024", score: 0.77, rating: "PG" },
    { id: "img_0010", dims: "2048×3072", score: 0.76, rating: "PG-13" },
    { id: "img_0011", dims: "1280×1920", score: 0.74, rating: "PG" },
    { id: "img_0012", dims: "1536×2048", score: 0.73, rating: "R" },
  ];

  // ===== 選択中画像インスペクタ（元 Qt: DatasetOverviewWidget + RatingScoreEditWidget） =====
  const RATINGS_S = ["PG", "PG-13", "R", "X", "XXX"];
  const TAGPOOL = ["1girl", "solo", "long_hair", "cherry_blossoms", "smile", "outdoors", "tree", "day", "hair_ornament", "lens_flare", "blurry_background", "looking_at_viewer", "upper_body", "sky"];
  // 多言語翻訳は単一実装 tagI18n.jsx を共有（genai-tag-db TAG_TRANSLATIONS 相当）。
  // 言語コードは DB 由来で en = danbooru canonical（保存値）。trTag/hasTr は (lang, tag)。
  const { LANGS, trTag: trTagAt, hasTr: hasTrAt } = window.LoRAIroTagI18n;
  const trTag = (t) => trTagAt(tagLang, t);
  const hasTr = (t) => hasTrAt(tagLang, t);
  const tagsFor = (id) => { const n = parseInt(id.slice(-2), 10) || 1; return TAGPOOL.slice(0, 6 + (n % 5)); };
  const baseScore = (im) => Math.round(im.score * 100) / 10;
  // 登録時にリサイズ・拡張子変換されるため、画像情報にはオリジナル画像のメタデータを表示。
  const aspectOf = (d) => { let [w, h] = d.split(String.fromCharCode(215)).map(Number); const g = (a, b) => b ? g(b, a % b) : a; const k = g(w, h); return (w / k) + ":" + (h / k); };
  const origMeta = (im) => {
    const n = parseInt(im.id.slice(-2), 10) || 1;
    const fmt = ["PNG", "JPEG", "WEBP"][n % 3];
    const alpha = fmt === "PNG" && n % 2 === 0;
    return { ext: "." + (fmt === "JPEG" ? "jpg" : fmt.toLowerCase()), fmt, dims: im.dims, aspect: aspectOf(im.dims), alpha };
  }; // aesthetic 0–1 → quality_score 0–10 の初期値
  const ar = (d) => d.replace("×", " / ");
  const thumbDims = (d) => { const [w, h] = d.split("×").map(Number); const s = 512 / Math.max(w, h); return Math.round(w * s) + "×" + Math.round(h * s); }; // サムネは長辺512px

  const [edits, setEdits] = React.useState({}); // { [id]: { rating, score, ratingEdited, scoreEdited } } — 画像ごとの手動編集
  const [tagLang, setTagLang] = React.useState("en"); // タグ表示言語 EN / 日本語
  const cur = images.find((im) => im.id === sel) || images[0];
  const e = edits[sel] || {};
  const curRating = e.rating != null ? e.rating : cur.rating;
  const curScore = e.score != null ? e.score : baseScore(cur);
  const changed = !!(e.ratingEdited || e.scoreEdited);
  const setImgRating = (v) => setEdits((p) => ({ ...p, [sel]: { ...(p[sel] || {}), rating: v, ratingEdited: true } }));
  const setImgScore = (v) => setEdits((p) => ({ ...p, [sel]: { ...(p[sel] || {}), score: v, scoreEdited: true } }));
  const saveImg = () => setEdits((p) => ({ ...p, [sel]: { ...(p[sel] || {}), rating: curRating, score: curScore, ratingEdited: false, scoreEdited: false } }));
  const resetImg = () => setEdits((p) => { const n = { ...p }; delete n[sel]; return n; });
  const srcTag = (edited) => edited
    ? <Chip kind="accent" dot="none">✎ MANUAL_EDIT</Chip>
    : <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", background: "var(--ink)", color: "var(--paper)", borderRadius: "var(--radius-badge)", padding: "1px 6px" }}>AI</span>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px minmax(0, 1fr) 340px", gap: "var(--gap-4)", alignItems: "start" }}>
      {/* ===== FILTER SIDEBAR ===== */}
      <div style={{ maxHeight: "calc(100vh - 200px)", overflow: "auto", paddingRight: 4 }}>
        {/* registration summary */}
        {regOpen && (
          <div style={{ border: "1px solid var(--ok-border)", background: "var(--ok-soft)", borderRadius: "var(--radius)", padding: "8px 10px", marginBottom: "var(--gap-2)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Chip kind="ok">登録完了</Chip>
              <span style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>shiba_batch_07 · 24枚 · 18.2s</span>
              <button onClick={() => setRegOpen(false)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--ink-soft)" }}>✕</button>
            </div>
            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink)" }}>
              新規 9 · 別版 3 · skip 12 · エラー 0
            </div>
            <div onClick={() => setShowSkips(!showSkips)} style={{ marginTop: 4, fontSize: "10px", color: "var(--accent)", cursor: "pointer" }}>
              {showSkips ? "▾" : "▸"} skip / 別版 の内訳
            </div>
            {showSkips && (
              <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 4 }}>
                {[["shiba_007_copy.jpg", "DUPLICATE", "同一 pHash → 自動 skip", "#4412"],
                  ["shiba_close_v2.jpg", "VARIANT", "属性差 (2048px) → 別版登録", "#12481"]].map(([f, t, d, ref]) => (
                  <div key={f} style={{ fontSize: "10px", color: "var(--ink-soft)", lineHeight: 1.5 }}>
                    <code style={{ fontFamily: "var(--font-mono)", color: "var(--ink)" }}>{f}</code> <span style={{ color: t === "VARIANT" ? "var(--warn)" : "var(--ink-faint)" }}>{t}</span><br />
                    {d} · <span style={{ color: "var(--accent)", cursor: "pointer" }}>{ref} を表示</span>
                  </div>
                ))}
                <span style={{ fontSize: "10px", color: "var(--ink-faint)" }}>…他 skip 10件 · 重複解決の手動操作は不要 (ADR 0061)</span>
              </div>
            )}
          </div>
        )}

        <Card bodyStyle={{ display: "block" }} style={{ padding: "4px 12px" }}>
          {/* query bar */}
          <Group label="クエリ Query">
            <div style={{ display: "flex", alignItems: "center", gap: 6, border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: "5px 8px", background: "var(--card)", flexWrap: "wrap" }}>
              <span style={{ color: "var(--ink-faint)" }}>⌕</span>
              <TagChip>1girl</TagChip>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--err)" }}>-lowres</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>"桜の下"</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>rating=PG-13</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>quality {qRange[0].toFixed(1)}–{qRange[1].toFixed(1)}</span>
              <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>追加はタイプ…</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
              <Chip kind="accent" dot="none">247 matches</Chip>
              <span style={{ flex: 1 }} />
              <Button size="small" variant="ghost" onClick={saveCurrentQuery}>☆ お気に入りに保存</Button>
            </div>
            {/* お気に入りの検索条件 */}
            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: "var(--gap-2)" }}>
              {savedQueries.map((q, i) => (
                <button key={q.name + i} type="button" onClick={() => setSavedActive(i)} title={q.sub} style={{
                  display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 8px",
                  borderRadius: "var(--radius-chip)", cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: "var(--fs-small)",
                  border: "1px solid " + (savedActive === i ? "var(--accent)" : "var(--line-strong)"),
                  background: savedActive === i ? "var(--accent-soft)" : "var(--card)",
                  color: savedActive === i ? "var(--accent-hover)" : "var(--ink)", fontWeight: savedActive === i ? 600 : 400,
                }}>
                  <span style={{ color: savedActive === i ? "var(--accent)" : "var(--ink-faint)" }}>★</span>
                  <span>{q.name}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)" }}>{q.sub}</span>
                  <span onClick={(e) => { e.stopPropagation(); setSavedQueries((qs) => qs.filter((_, j) => j !== i)); }} style={{ color: "var(--ink-faint)", paddingLeft: 2 }}>×</span>
                </button>
              ))}
            </div>
          </Group>

          {/* quality score — 範囲選択（下限・上限）*/}
          <Group label="品質スコア quality" sub="quality_score 0–10">
            <RangeSlider min={0} max={10} step={0.5} value={qRange} onChange={setQRange}
              format={(v) => v.toFixed(1)} />
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", margin: "2px 0 6px" }}>
              {qRange[0].toFixed(1)} – {qRange[1].toFixed(1)} の範囲
            </div>
            <div style={{ fontSize: "10px", color: "var(--ink-soft)", marginBottom: 4 }}>未採点 no-score:</div>
            <SegmentedControl size="small" value={noScore} onChange={setNoScore}
              options={[{ value: "exclude", label: "除外" }, { value: "include", label: "含める" }, { value: "only", label: "未採点のみ" }]} />
          </Group>

          {/* rating by source */}
          <Group label="rating" sub="by source">
            <div style={{ fontSize: "10px", color: "var(--ink-soft)", margin: "0 0 5px" }}>AI レーティング <code style={{ fontFamily: "var(--font-mono)" }}>Model</code></div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--gap-2)" }}>
              {aiRatings.map(([r, n]) => <RatingChip key={r} label={r} count={n} on={aiSel.includes(r)} onClick={() => toggleIn(setAiSel)(r)} dim={r.startsWith("未")} />)}
            </div>
            <div style={{ fontSize: "10px", color: "var(--ink-soft)", margin: "10px 0 5px" }}>✎ 手動レーティング <code style={{ fontFamily: "var(--font-mono)" }}>MANUAL_EDIT</code></div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--gap-2)" }}>
              {manualRatings.map(([r, n]) => <RatingChip key={r} label={r} count={n} on={manualSel.includes(r)} onClick={() => toggleIn(setManualSel)(r)} dim={r.startsWith("な")} />)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <span style={{ fontSize: "10px", color: "var(--ink-soft)" }}>複合 combine:</span>
              <SegmentedControl size="small" value={ratingCombine} onChange={setRatingCombine} options={["AND", "OR"]} />
            </div>
            <div style={{ marginTop: 6, fontSize: "10px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
              AI≠手動 の不一致 112 · 手動で上書き済 668（ADR 0015/0031）
            </div>
          </Group>

          {/* annotations state */}
          <Group label="annotations state" sub="Tag/Caption joins">
            <Facet label="tags" count="9,820" checked={facets.tags} onToggle={() => tgl("tags")} />
            <Facet label="caption" count="2,140" checked={facets.caption} onToggle={() => tgl("caption")} />
            <Facet label="textファイル由来 from text" count="3,810" checked={facets.fromText} onToggle={() => tgl("fromText")} />
            <Facet label="手動編集あり manually edited" count="668" checked={facets.edited} onToggle={() => tgl("edited")} strong />
            {facets.edited && (
              <div style={{ paddingLeft: 20, color: "var(--ink-soft)" }}>
                <Facet label="tag" count="540" checked={false} onToggle={() => {}} />
                <Facet label="caption" count="120" checked={false} onToggle={() => {}} />
                <Facet label="score" count="8" checked={false} onToggle={() => {}} />
              </div>
            )}
          </Group>

          {/* model filter */}
          <Group label="model filter" sub="Model.name">
            <Input placeholder="モデル名で検索…" style={{ fontSize: "var(--fs-small)", padding: "4px 8px" }} />
            <div style={{ fontSize: "10px", color: "var(--ink-soft)", margin: "6px 0 2px" }}>ピン留め pinned · 2</div>
            <Facet label="wd-v1-4-tagger" count="9,200" checked onToggle={() => {}} />
            <Facet label="gpt-4o-caption" count="2,140" checked={false} onToggle={() => {}} />
            <div style={{ fontSize: "10px", color: "var(--ink-soft)", margin: "6px 0 2px" }}>最近使用 recent</div>
            <Facet label="claude-3-5-sonnet" count="810" checked={false} onToggle={() => {}} />
            <Facet label="deepdanbooru" count="1,420" checked={false} onToggle={() => {}} />
            {showMoreModels && [["wd-eva02-large", 6100], ["moondream3", 320], ["musiq", 540]].map(([m, n]) => (
              <Facet key={m} label={m} count={n.toLocaleString()} checked={false} onToggle={() => {}} dim />
            ))}
            <div onClick={() => setShowMoreModels(!showMoreModels)} style={{ fontSize: "10px", color: "var(--accent)", cursor: "pointer", marginTop: 4 }}>
              {showMoreModels ? "− 折りたたむ" : "+ 他 14 モデルを表示 (合計 18)"}
            </div>
          </Group>

          {/* date — スライダーで範囲選択（開始・終了）*/}
          <Group label="date" sub="Image.created_at">
            <div style={{ display: "flex", alignItems: "flex-end", gap: 1, height: 30, marginBottom: 2 }}>
              {bars.map((h, i) => { const within = i >= (dateRange[0] / DAYS) * bars.length && i <= (dateRange[1] / DAYS) * bars.length; return <div key={i} style={{ flex: 1, height: (h * 30) + "px", background: within ? "var(--accent)" : "var(--line-strong)", borderRadius: "1px 1px 0 0" }} />; })}
            </div>
            <RangeSlider min={0} max={DAYS} step={1} value={dateRange} onChange={setDateRange}
              format={(v) => dayLabel(v).slice(5)} />
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", marginTop: 4 }}>{dayLabel(dateRange[0])} – {dayLabel(dateRange[1])}</div>
          </Group>

          {/* error state */}
          <Group label="エラー状態 error state" sub="ErrorRecord">
            <SegmentedControl size="small" value={errState} onChange={setErrState}
              options={[{ value: "all", label: "all" }, { value: "only", label: "エラーのみ", count: 42 }, { value: "exclude", label: "除外" }]} />
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", marginTop: 6 }}>unresolved 42 · resolved 318</div>
          </Group>
        </Card>
      </div>

      {/* ===== RESULTS ===== */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-3)", marginBottom: 10, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>検索結果</h2>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>並び score(aesthetic)↓ · 247 件 · staged {staged}枚</span>
          <span style={{ flex: 1 }} />
          <Button size="small" onClick={() => onStage(sel)}>選択をステージへ</Button>
          <Button size="small" variant="ghost">サムネイル ▾</Button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(132px,1fr))", gap: "var(--gap-3)" }}>
          {images.map((im) => (
            <Thumbnail key={im.id} label={im.id} dims={im.dims} score={im.score} rating={im.rating}
              selected={sel === im.id} onClick={() => setSel(im.id)} />
          ))}
        </div>
        <div style={{ marginTop: "var(--gap-2)", paddingTop: "var(--gap-2)", borderTop: "1px solid var(--line)" }}>
          <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--ink-faint)" }}>
            サムネ右上 = Score (top model) · 右下 = Rating · 左下 = width × height
          </span>
        </div>

        {/* ===== STAGE TRAY — shared staged-image thumbnail strip (StageStrip) ===== */}
        <window.StageStrip
          staged={staged}
          caption="3 クエリ · staged.image_id を models.* 経由でバッチ実行 → ErrorRecord に集約"
          style={{ marginTop: "var(--gap-3)" }}
          action={
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
              <Button size="small" variant="primary">▶ Annotate {staged} →</Button>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>⌘↵</span>
            </div>
          }
        />
      </div>

      {/* ===== 選択中画像インスペクタ — プレビュー + タグ情報 + 評価・スコア手動編集（即時） ===== */}
      <div style={{ position: "sticky", top: "var(--gap-2)", maxHeight: "calc(100vh - 180px)", overflow: "auto", display: "flex", flexDirection: "column", gap: "var(--gap-3)", paddingRight: 2 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontSize: "var(--fs-small)", fontWeight: 700, letterSpacing: "var(--letter-caps)", textTransform: "uppercase", color: "var(--ink)" }}>選択中</span>
          <code style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>{cur.id}</code>
          <span style={{ flex: 1 }} />
          {changed && <Chip kind="accent" dot="none">✎ 未保存</Chip>}
        </div>

        {/* プレビュー（ImagePreviewWidget） */}
        <div style={{ position: "relative", width: "100%", aspectRatio: "1 / 1", border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", overflow: "hidden", background: "var(--paper-shade)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ height: "88%", aspectRatio: ar(cur.dims), border: "1px solid var(--line)", background: "repeating-linear-gradient(135deg, var(--paper-shade) 0 8px, var(--card) 8px 16px)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>{cur.id}</span>
          </div>
          <span style={{ position: "absolute", bottom: 8, right: 8, fontFamily: "var(--font-mono)", fontSize: "10px", background: "var(--card)", border: "1px solid var(--line)", borderRadius: "var(--radius-badge)", padding: "1px 6px", color: "var(--ink-soft)" }}>{thumbDims(cur.dims)} · 512px thumb</span>
        </div>

        {/* 画像情報（metadataGroupBox）— 登録時にリサイズ/変換されるためオリジナル画像のメタデータを表示 */}
        <Card title="画像情報" aside={<span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", color: "var(--ink-faint)" }}>ORIGINAL</span>}>
          {(() => { const o = origMeta(cur); return (
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: "var(--gap-2)", rowGap: 4, fontSize: "var(--fs-small)" }}>
              {[["ファイル名", cur.id + o.ext], ["拡張子", o.fmt], ["解像度", o.dims + " px"], ["アスペクト比", o.aspect], ["アルファチャンネル", o.alpha ? "あり RGBA" : "なし RGB"]].map(([k, v]) => (
                <React.Fragment key={k}>
                  <span style={{ color: "var(--ink-soft)", whiteSpace: "nowrap" }}>{k}:</span>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--ink)", textAlign: "right", wordBreak: "break-all" }}>{v}</span>
                </React.Fragment>
              ))}
            </div>
          ); })()}
          <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
            オリジナル画像のメタデータ · 登録時にリサイズ・拡張子変換して保存
          </div>
        </Card>

        {/* タグ情報（annotationGroupBox · tags） — 表示言語切替（TAG_TRANSLATIONS 相当・多言語） */}
        <Card title="タグ" aside={<div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>{tagsFor(cur.id).length} tags</span>
          <select value={tagLang} onChange={(ev) => setTagLang(ev.target.value)} title="表示言語 Translation" style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink)", background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", padding: "2px 4px", cursor: "pointer" }}>
            {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </div>}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {tagsFor(cur.id).map((t) => (
              <TagChip key={t} title={tagLang === "en" ? t : t + " → " + trTag(t)} style={!hasTr(t) ? { borderStyle: "dashed", color: "var(--ink-faint)" } : undefined}>{trTag(t)}</TagChip>
            ))}
          </div>
          {tagLang !== "en" && (
            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
              表示のみ翻訳（{tagLang}）· 保存値は danbooru canonical 固定· 点線 = 翻訳なし
            </div>
          )}
        </Card>

        {/* 評価・スコア編集（RatingScoreEditWidget） — AI と 人間（手動）を分けて表示 */}
        <Card style={{ borderColor: "var(--accent-border)", borderLeft: "3px solid var(--accent)" }}
          title={<span style={{ color: "var(--accent)", fontWeight: 700 }}>評価・スコア編集</span>}>
          {(() => { const aiRating = cur.rating; const aiScore = baseScore(cur); return (
          <React.Fragment>
            {/* ===== AI（読み取り専用）===== */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", background: "var(--ink)", color: "var(--paper)", borderRadius: "var(--radius-badge)", padding: "1px 6px" }}>AI</span>
              <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>モデル推論値 · 読み取り専用</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <span style={{ width: 44, flex: "none", fontSize: "10px", color: "var(--ink-soft)" }}>Rating</span>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {RATINGS_S.map((r) => (
                  <span key={r} style={{ padding: "2px 7px", borderRadius: "var(--radius-chip)", fontSize: "10px", fontFamily: "var(--font-mono)",
                    border: "1px solid " + (r === aiRating ? "var(--line-strong)" : "transparent"),
                    background: r === aiRating ? "var(--paper-shade)" : "transparent",
                    color: r === aiRating ? "var(--ink)" : "var(--ink-faint)", fontWeight: r === aiRating ? 600 : 400 }}>{r}</span>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 44, flex: "none", fontSize: "10px", color: "var(--ink-soft)" }}>スコア</span>
              <div style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--paper-shade)", overflow: "hidden" }}>
                <div style={{ width: aiScore * 10 + "%", height: "100%", background: "var(--ink-faint)" }} />
              </div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", width: 40, textAlign: "right", color: "var(--ink-soft)" }}>{aiScore.toFixed(2)}</span>
            </div>

            {/* ===== 人間（手動・編集可能）===== */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, margin: "var(--gap-3) 0 6px", paddingTop: "var(--gap-3)", borderTop: "1px solid var(--line)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", color: "var(--accent)", fontWeight: 700 }}>✎ 人間</span>
              <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>手動レーティング・スコア</span>
              <span style={{ flex: 1 }} />
              {(e.ratingEdited || e.scoreEdited) && <Chip kind="accent" dot="none">MANUAL_EDIT</Chip>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <span style={{ width: 44, flex: "none", fontSize: "10px", color: "var(--ink-soft)" }}>Rating</span>
              <div style={{ flex: 1 }}>
                <SegmentedControl size="small" value={curRating} onChange={setImgRating} options={RATINGS_S.map((r) => ({ value: r, label: r }))} />
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 44, flex: "none", fontSize: "10px", color: "var(--ink-soft)" }}>スコア</span>
              <input type="range" min="0" max="10" step="0.1" value={curScore} onChange={(ev) => setImgScore(parseFloat(ev.target.value))} style={{ flex: 1, accentColor: "var(--accent)" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", width: 40, textAlign: "right" }}>{Number(curScore).toFixed(2)}</span>
            </div>
            <div style={{ marginTop: 8 }}><ProgressBar value={curScore * 10} tone="ok" /></div>
            {(e.scoreEdited && Math.abs(curScore - aiScore) > 0.001) && (
              <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--accent)" }}>
                Δ {(curScore - aiScore >= 0 ? "+" : "") + (curScore - aiScore).toFixed(2)} vs AI
              </div>
            )}
            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.5 }}>quality_score 0–10（ADR 0029）· AI と source 分離 · 手動補正は <code>is_edited_manually</code></div>
          </React.Fragment>
          ); })()}

          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", marginTop: "var(--gap-3)" }}>
            <span style={{ flex: 1 }} />
            <Button size="small" variant="ghost" onClick={resetImg}>取消</Button>
            <Button size="small" variant="primary" onClick={saveImg}>保存</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

window.SearchScreen = SearchScreen;
