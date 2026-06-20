// FRAME 5B · TAG EDIT — inline tag-edit detail (Results 行 → Detail).
// ディテールヘッダは元 Qt 実装（DatasetOverviewWidget）に準拠して配置:
//   mainSplitter(Horizontal) = [ 画像情報 左 | プレビュー 右 ]
//     ・左 infoContainer  = infoSplitter(Vertical): 画像情報フォーム / 評価・スコア編集
//       （metadataGroupBox = ファイル名 / 画像パス / 拡張子 / フォーマット / モード /
//        アルファチャンネル / 解像度 / アスペクト比, QFormLayout の label:value）
//     ・右 imageContainer = ImagePreview（プレビュー）+ ThumbnailSelectorWidget（サムネイル列）
// 下部 = TAGS / CAPTION を全幅で編集。評価・スコアは RatingScoreEditWidget 相当。
// 非破壊: × でタグ soft-reject（rejected_at・行は残す）、+ で is_edited_manually
// =true の手動タグ。rating / score の手動変更も MANUAL_EDIT として記録。
// score は ADR 0029 の quality_score (0–10)。
// 注: 実 LoRAIro では per-tag confidence は破棄され DB は None。confidence
// 数値・閾値表示は持たない。DS プリミティブのみで構成。
const DS_TAGEDIT = window.LoRAIroDesignSystem_64d8f7;

const RATINGS = ["PG", "PG-13", "R", "X", "XXX"];

function TagEditScreen() {
  const { Card, Button, Chip, TagChip, ProgressBar, SegmentedControl } = DS_TAGEDIT;

  const [idx, setIdx] = React.useState(0);
  const total = 9;

  // 元 Qt metadataGroupBox（画像情報）の field 構成。QFormLayout の label:value。
  const META = [
    ["ファイル名", "img_04" + (18 + idx) + ".webp"],
    ["画像パス", "…/main_dataset_20260601_001/04" + (18 + idx)],
    ["拡張子", ".webp"],
    ["フォーマット", "WEBP"],
    ["モード", "RGB"],
    ["アルファチャンネル", "なし"],
    ["解像度", "2048×3072"],
    ["アスペクト比", "2 : 3"],
  ];

  const initialTags = [
    { t: "1girl" }, { t: "solo" }, { t: "long_hair" }, { t: "cherry_blossoms" },
    { t: "smile" }, { t: "outdoors" }, { t: "tree" }, { t: "day" },
    { t: "hair_ornament" }, { t: "lens_flare" }, { t: "blurry_background" },
  ];
  const [tags, setTags] = React.useState(initialTags);
  const [rejected, setRejected] = React.useState([]);
  const [draft, setDraft] = React.useState("");
  const [tagLang, setTagLang] = React.useState("en"); // タグ表示言語（表示のみ翻訳・保存値は canonical 固定）

  // 多言語翻訳は SearchScreen の選択画像インスペクタと同じ単一実装 tagI18n.jsx を共有。
  const { LANGS, trTag: trTagAt, hasTr: hasTrAt } = window.LoRAIroTagI18n;
  const trTag = (t) => trTagAt(tagLang, t);
  const hasTr = (t) => hasTrAt(tagLang, t);

  // manual annotations
  const [rating, setRating] = React.useState("PG-13"); // AI 由来の初期値
  const [ratingEdited, setRatingEdited] = React.useState(false);
  const [score, setScore] = React.useState(8.2);
  const [scoreEdited, setScoreEdited] = React.useState(false);

  const reject = (t) => { setTags((xs) => xs.filter((x) => x.t !== t)); setRejected((r) => [...r, t]); };
  const restore = (t) => { setRejected((r) => r.filter((x) => x !== t)); setTags((xs) => [...xs, { t }]); };
  const add = () => { const v = draft.trim(); if (!v) return; setTags((xs) => [...xs, { t: v, manual: true }]); setDraft(""); };
  const setRatingManual = (v) => { setRating(v); setRatingEdited(true); };
  const setScoreManual = (v) => { setScore(v); setScoreEdited(true); };

  const sourceTag = (edited) => edited
    ? <Chip kind="accent" dot="none">✎ MANUAL_EDIT</Chip>
    : <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", background: "var(--ink)", color: "var(--paper)", borderRadius: "var(--radius-badge)", padding: "1px 6px" }}>AI</span>;

  const changeCount = rejected.length + tags.filter((t) => t.manual).length + (ratingEdited ? 1 : 0) + (scoreEdited ? 1 : 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-3)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>タグ編集</h2>
        <Chip kind="neutral" dot="none">非破壊 non-destructive</Chip>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>batch #J-0418</span>
      </div>

      {/* ===== DETAIL HEADER — 元 Qt DatasetOverviewWidget 準拠（画像情報 左 | プレビュー 右） ===== */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 340px) 1fr", gap: "var(--gap-4)", alignItems: "start" }}>

        {/* === 左: infoContainer（infoSplitter Vertical: 画像情報 / 評価・スコア編集） === */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>

          {/* metadataGroupBox — 画像情報（QFormLayout label:value） */}
          <Card title="画像情報" aside={<span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>image_id 12{481 + idx}</span>}>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: "var(--gap-3)", rowGap: 5, fontSize: "var(--fs-small)", lineHeight: 1.5 }}>
              {META.map(([k, v]) => (
                <React.Fragment key={k}>
                  <span style={{ color: "var(--ink-soft)", whiteSpace: "nowrap" }}>{k}:</span>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--ink)", textAlign: "right", wordBreak: "break-all" }}>{v}</span>
                </React.Fragment>
              ))}
            </div>
            <div style={{ marginTop: "var(--gap-2)", paddingTop: "var(--gap-2)", borderTop: "1px solid var(--line)", fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.6 }}>
              + ProcessedImage · upscaler RealESRGAN_x4 &nbsp;·&nbsp; phash a3f1·c8e0
            </div>
          </Card>

          {/* RatingScoreEditWidget — 評価・スコア編集 */}
          <Card style={{ borderColor: "var(--accent-border)", borderLeft: "3px solid var(--accent)" }}
            title={<span style={{ color: "var(--accent)", fontWeight: 700 }}>評価・スコア編集</span>}
            aside={<Chip kind="accent" dot="none">✎ 手動入力</Chip>}>
            {/* Rating */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <span style={{ fontSize: "var(--fs-small)", fontWeight: 600 }}>Rating</span>
              <span style={{ flex: 1 }} />
              {sourceTag(ratingEdited)}
            </div>
            <SegmentedControl size="small" value={rating} onChange={setRatingManual}
              options={RATINGS.map((r) => ({ value: r, label: r }))} />
            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
              Rating.normalized_rating — 手動設定は <code>is_edited_manually</code>（AI 値と source 分離）
            </div>

            {/* Score */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, margin: "var(--gap-3) 0 5px", paddingTop: "var(--gap-3)", borderTop: "1px solid var(--line)" }}>
              <span style={{ fontSize: "var(--fs-small)", fontWeight: 600 }}>スコア</span>
              <span style={{ flex: 1 }} />
              {sourceTag(scoreEdited)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)" }}>
              <input type="range" min="0" max="10" step="0.1" value={score} onChange={(e) => setScoreManual(parseFloat(e.target.value))} style={{ flex: 1, accentColor: "var(--accent)" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", width: 40, textAlign: "right" }}>{score.toFixed(2)}</span>
            </div>
            <div style={{ marginTop: 8 }}><ProgressBar value={score * 10} tone="ok" /></div>
            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)" }}>quality_score · 0–10（ADR 0029）— 手動補正は <code>is_edited_manually</code></div>
          </Card>
        </div>

        {/* === 右: imageContainer（ImagePreview + ThumbnailSelectorWidget） === */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}>
          {/* labelPreviewTitle */}
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-2)" }}>
            <span style={{ fontSize: "var(--fs-small)", fontWeight: 600, color: "var(--ink-soft)" }}>プレビュー</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>img_04{18 + idx}.webp</span>
          </div>

          {/* ImagePreview — previewGraphicsView */}
          <div style={{
            position: "relative", width: "100%", height: 440,
            border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", overflow: "hidden",
            background: "var(--paper-shade)", display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <div style={{
              height: "92%", aspectRatio: "2 / 3", border: "1px solid var(--line)",
              background: "repeating-linear-gradient(135deg, var(--paper-shade) 0 9px, var(--card) 9px 18px)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>img_04{18 + idx}</span>
            </div>
            <span style={{ position: "absolute", bottom: 8, right: 8, fontFamily: "var(--font-mono)", fontSize: "10px", background: "var(--card)", border: "1px solid var(--line)", borderRadius: "var(--radius-badge)", padding: "1px 6px", color: "var(--ink)" }}>2048×3072 · 100%</span>
          </div>

          {/* ThumbnailSelectorWidget — サムネイル列 */}
          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)" }}>
            <Button size="small" variant="ghost" onClick={() => setIdx((i) => Math.max(0, i - 1))}>◂</Button>
            <div style={{ flex: 1, display: "flex", gap: 4, overflowX: "auto", padding: "2px 0" }}>
              {Array.from({ length: total }).map((_, i) => (
                <button key={i} onClick={() => setIdx(i)} title={"img_04" + (18 + i)} style={{
                  flex: "none", width: 36, aspectRatio: "2 / 3", cursor: "pointer", padding: 0,
                  border: i === idx ? "2px solid var(--accent)" : "1px solid var(--line)",
                  borderRadius: "var(--radius-badge)", overflow: "hidden",
                  background: "repeating-linear-gradient(135deg, var(--paper-shade) 0 5px, var(--card) 5px 10px)",
                }} />
              ))}
            </div>
            <span style={{ flex: "none", fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{idx + 1} / {total}</span>
            <Button size="small" variant="ghost" onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}>▸</Button>
          </div>
        </div>
      </div>

      {/* ===== TAGS（全幅） ===== */}
      <Card title="TAGS" aside={<div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>wd-v1-4-tagger · {tags.length} tags</span>
        <select value={tagLang} onChange={(ev) => setTagLang(ev.target.value)} title="表示言語 Translation" style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink)", background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius)", padding: "2px 4px", cursor: "pointer" }}>
          {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>
      </div>}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--gap-2)" }}>
          {tags.map((x) => {
            const untr = tagLang !== "en" && !hasTr(x.t);
            const st = {};
            if (x.manual) st.borderColor = "var(--accent)";
            if (untr) { st.borderStyle = "dashed"; st.color = "var(--ink-faint)"; }
            return (
              <TagChip key={x.t} onRemove={() => reject(x.t)}
                title={tagLang === "en" ? x.t : x.t + " → " + trTag(x.t)}
                style={Object.keys(st).length ? st : undefined}>
                {trTag(x.t)}
                {x.manual && <span style={{ marginLeft: 4, color: "var(--accent)" }}>✎</span>}
              </TagChip>
            );
          })}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, border: "1px dashed var(--line-strong)", borderRadius: "var(--radius-chip)", padding: "1px 4px 1px 8px" }}>
            <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="手動タグ…" style={{ border: "none", outline: "none", background: "transparent", fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", width: 92, color: "var(--ink)" }} />
            <Button size="small" variant="ghost" onClick={add}>+</Button>
          </span>
        </div>
        <div style={{ marginTop: 8, fontSize: "10px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
          × で soft-reject（<code style={{ fontFamily: "var(--font-mono)" }}>rejected_at</code> に記録、行は残す）· ✎ は手動追加
        </div>
        {tagLang !== "en" && (
          <div style={{ marginTop: 4, fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-faint)", lineHeight: 1.5 }}>
            表示のみ翻訳（{tagLang}）· 保存値は danbooru canonical 固定 · 点線 = 翻訳なし
          </div>
        )}
        {rejected.length > 0 && (
          <div style={{ marginTop: 8, borderTop: "1px dashed var(--line)", paddingTop: 8 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", marginBottom: 4 }}>soft-rejected · {rejected.length}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--gap-2)" }}>
              {rejected.map((t) => (
                <span key={t} onClick={() => restore(t)} style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)", textDecoration: "line-through", cursor: "pointer", border: "1px solid var(--line)", borderRadius: "var(--radius-chip)", padding: "1px 8px" }}>
                  {t} <span style={{ color: "var(--accent)", textDecoration: "none" }}>↺</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* ===== CAPTION（全幅） ===== */}
      <Card title="CAPTION" aside={<span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)" }}>gpt-4o-caption</span>}>
        <div style={{ fontSize: "var(--fs-base)", lineHeight: 1.6, color: "var(--ink)" }}>
          A young woman with long hair stands beneath blooming cherry blossoms, smiling softly in daylight.
        </div>
      </Card>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", paddingTop: "var(--gap-2)", borderTop: "1px solid var(--line)" }}>
        <Chip kind="ok">変更 {changeCount} 件</Chip>
        <span style={{ flex: 1 }} />
        <Button size="small" variant="ghost">取消</Button>
        <Button size="small" variant="primary">保存して次へ ▸</Button>
      </div>
    </div>
  );
}

window.TagEditScreen = TagEditScreen;
