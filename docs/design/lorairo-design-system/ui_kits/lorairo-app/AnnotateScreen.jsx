// AnnotateScreen — pipeline (output-table × ModelType) + model picker modal
// (environment → task → model two-stage filter). Follows Wireframes v12
// Frame 3A (pipeline) + 3B (model picker) and model_selection_widget.py.
const DS_ANNOTATE = window.LoRAIroDesignSystem_64d8f7;

// ---- pipeline stage model (assigned primaries + derived shadow outputs) ----
const STAGES = [
  {
    key: "TAGS", n: 2, of: 4, config: "conf ≥ 0.35 · 最大40タグ",
    models: [{ name: "wd-v1-4-tagger" }, { name: "wd-eva02-large-tagger" }],
    derived: [{ name: "gpt-4o-caption", from: "CAPTION" }],
  },
  {
    key: "CAPTION", n: 1, of: 5, config: "lang: ja · 最大140字",
    models: [{ name: "gpt-4o-caption", multi: true, fills: "T S" }],
    derived: [],
  },
  {
    key: "SCORE", n: 2, of: 3, config: "overwrite=off · score → quality_score",
    models: [{ name: "aesthetic-v2" }, { name: "musiq" }],
    derived: [{ name: "gpt-4o-caption", from: "CAPTION" }],
  },
  {
    key: "RATING", n: 1, of: 2, config: "conf ≥ 0.5 · multimodal 派生なし †",
    models: [{ name: "wd-rating-v2" }],
    derived: [],
  },
];

// ---- model catalog — env × annotation-type × provider で絞り込み可能 ----
// types: tags / caption / score / rating。API はマルチモーダルで複数 type を 1 推論で取得。
const TYPE_OF = { TAGS: "tags", CAPTION: "caption", SCORE: "score", RATING: "rating" };
const TYPE_LABEL = { tags: "タグ", caption: "キャプション", score: "スコア", rating: "レーティング" };
const ALL_MODELS = [
  { name: "gpt-4o-caption", ver: "2024-08-06", provider: "OpenAI", env: "api", types: ["caption", "tags", "score", "rating"], multi: true, chip: ["ok", "API ready"], cost: "$0.005/img", min: 0.50, avg: 0.86, rec: true },
  { name: "claude-3-5-sonnet", ver: "20241022", provider: "Anthropic", env: "api", types: ["caption", "tags", "score", "rating"], multi: true, chip: ["ok", "API ready"], cost: "$0.012/img", min: 0.50, avg: 0.81, rec: true },
  { name: "gemini-1.5-pro", ver: "latest", provider: "Google", env: "api", types: ["caption", "tags", "score", "rating"], multi: true, chip: ["warn", "needs key →⚙"], cost: "$0.004/img", needsKey: true },
  { name: "gpt-4-vision-preview", ver: "2023-12", provider: "OpenAI", env: "api", types: ["caption", "tags"], multi: true, chip: ["muted", "discontinued"], cost: "—", disabled: true },
  { name: "wd-v1-4-tagger", ver: "v1.4", provider: "SmilingWolf", env: "local", types: ["tags"], chip: ["ok", "local"], cost: "GPU ~0.3s", min: 0.35, avg: 0.62, gpu: true, rec: true },
  { name: "wd-eva02-large-tagger", ver: "v3", provider: "SmilingWolf", env: "local", types: ["tags"], chip: ["ok", "local"], cost: "GPU ~0.5s", min: 0.35, avg: 0.66, gpu: true },
  { name: "deepdanbooru", ver: "v4", provider: "KichangKim", env: "local", types: ["tags"], chip: ["ok", "local"], cost: "GPU ~0.4s", min: 0.50, avg: 0.58, gpu: true },
  { name: "aesthetic-v2", ver: "v2", provider: "LAION", env: "local", types: ["score"], chip: ["ok", "local"], cost: "CPU ~0.1s", rec: true },
  { name: "musiq", ver: "—", provider: "Google", env: "local", types: ["score"], chip: ["ok", "local"], cost: "GPU ~0.2s", gpu: true },
  { name: "wd-rating-v2", ver: "v2", provider: "SmilingWolf", env: "local", types: ["rating"], chip: ["ok", "local"], cost: "GPU ~0.3s", gpu: true, rec: true },
  { name: "llava-next-13b", ver: "13b", provider: "LLaVA", env: "local", types: ["caption", "tags"], multi: true, chip: ["ok", "local"], cost: "GPU ~2s", gpu: true },
  { name: "qwen-vl-chat", ver: "7b", provider: "Alibaba", env: "local", types: ["caption"], chip: ["ok", "local"], cost: "GPU ~1.5s", gpu: true },
];

function ModelPicker({ stage, onClose }) {
  const { Button, Chip, TypeBadge, SegmentedControl } = DS_ANNOTATE;
  const TASK_OF = { TAGS: "Tags", CAPTION: "Caption", SCORE: "Scores", RATING: "Rating" };
  const taskLabel = TASK_OF[stage] || stage;
  const [env, setEnv] = React.useState("all"); // executionEnvCombo: all / api / local
  const [provider, setProvider] = React.useState("all");
  const envLabel = env === "all" ? "全環境" : env === "api" ? "Web API" : "ローカル";
  const stageType = TYPE_OF[stage] || "all";
  const [atype, setAtype] = React.useState(stageType); // アノテーション種類フィルタ
  const [selected, setSelected] = React.useState(() => new Set(ALL_MODELS.filter((m) => m.rec).map((m) => m.name)));
  const [recMode, setRecMode] = React.useState(true);
  const changeEnv = (v) => { setEnv(v); setProvider("all"); };
  const match = (m, e, t, p) => (e === "all" || m.env === e) && (t === "all" || m.types.includes(t)) && (p === "all" || m.provider === p);
  const filtered = ALL_MODELS.filter((m) => match(m, env, atype, provider));
  const typeCount = (t) => ALL_MODELS.filter((m) => match(m, env, t, provider)).length;
  const provCount = (p) => ALL_MODELS.filter((m) => match(m, env, atype, p)).length;
  const provsInEnv = [...new Set(ALL_MODELS.filter((m) => env === "all" || m.env === env).map((m) => m.provider))];
  const toggle = (m) => { if (m.disabled) return; setRecMode(false); setSelected((s) => { const n = new Set(s); n.has(m.name) ? n.delete(m.name) : n.add(m.name); return n; }); };
  const selectAll = () => { setRecMode(false); setSelected((s) => { const n = new Set(s); filtered.forEach((m) => { if (!m.disabled) n.add(m.name); }); return n; }); };
  const deselectAll = () => { setRecMode(false); setSelected((s) => { const n = new Set(s); filtered.forEach((m) => n.delete(m.name)); return n; }); };
  const selectRec = () => { setRecMode(true); setSelected(new Set(ALL_MODELS.filter((m) => m.rec).map((m) => m.name))); };
  const selCount = selected.size;
  const stageSel = ALL_MODELS.filter((m) => selected.has(m.name) && (stageType === "all" || m.types.includes(stageType)));

  const RailGroup = ({ n, title, sub, children }) => (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ width: 14, height: 14, flex: "none", borderRadius: "50%", background: "var(--accent)", color: "#fff", fontSize: 9, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>{n}</span>
        <span style={{ fontSize: "var(--fs-small)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "var(--letter-caps)" }}>{title}</span>
        {sub && <code style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-faint)" }}>{sub}</code>}
      </div>
      {children}
    </div>
  );
  const Radio = ({ label, count, on, onClick, dim }) => (
    <div onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 7, padding: "3px 4px", cursor: "pointer", fontSize: "var(--fs-small)", color: dim ? "var(--ink-faint)" : "var(--ink)" }}>
      <span style={{ width: 12, height: 12, flex: "none", borderRadius: "50%", border: "1px solid " + (on ? "var(--accent)" : "var(--line-strong)"), background: on ? "var(--accent)" : "var(--card)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 8 }}>{on ? "●" : ""}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)" }}>{count}</span>}
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "var(--scrim)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 900, maxWidth: "94vw", maxHeight: "88vh", display: "flex", flexDirection: "column", background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-shell)", boxShadow: "var(--shadow-shell)", overflow: "hidden" }}>
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "10px 16px", background: "var(--paper-shade)", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontWeight: 600 }}>{stage} のモデル選択</span>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>実行環境で絞り込み → 推奨/手動で選択 · staged 9枚</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>フィルタ: <b style={{ color: "var(--ink)" }}>{envLabel} / {atype === "all" ? "全種類" : TYPE_LABEL[atype]}</b></span>
          <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, color: "var(--ink-soft)" }}>✕</button>
        </div>

        {/* presets */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderBottom: "1px solid var(--line)", flexWrap: "wrap" }}>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>presets:</span>
          {[["All installed", 12], ["Multimodal only", 6], ["Cheap (local)", 4], ["High-fidelity API", 3]].map(([p, n]) => (
            <Chip key={p} kind="neutral" dot="none">{p} {n}</Chip>
          ))}
          <span style={{ flex: 1 }} />
          <code style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-faint)" }}>⌘F 検索 · ⌘A 表示分を全選択</code>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "230px 1fr", flex: 1, minHeight: 0 }}>
          {/* left rail: フィルタの仕組みを明示（元 Qt ModelSelectionWidget の executionEnv + DB 自動選択） */}
          <div style={{ borderRight: "1px solid var(--line)", padding: "4px 14px", overflow: "auto" }}>
            <RailGroup n="1" title="アノテーション種類" sub="type_filter">
              <Radio label="すべて" count={typeCount("all")} on={atype === "all"} onClick={() => setAtype("all")} />
              {["tags", "caption", "score", "rating"].map((t) => (
                <Radio key={t} label={TYPE_LABEL[t]} count={typeCount(t)} on={atype === t} onClick={() => setAtype(t)} dim={typeCount(t) === 0} />
              ))}
              <div style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.5 }}>{stage} は既定で「{stageType === "all" ? "すべて" : TYPE_LABEL[stageType]}」。その種類を出力できるモデルだけ候補に。</div>
            </RailGroup>
            <RailGroup n="2" title="Provider" sub="grouping">
              <Radio label="all" count={provCount("all")} on={provider === "all"} onClick={() => setProvider("all")} />
              {provsInEnv.map((p) => (
                <Radio key={p} label={p} count={provCount(p)} on={provider === p} onClick={() => setProvider(p)} dim={provCount(p) === 0} />
              ))}
            </RailGroup>
            <div style={{ marginTop: 10, padding: "8px 10px", border: "1px dashed var(--line-strong)", borderRadius: "var(--radius)", background: "var(--paper-shade)", fontSize: 10, color: "var(--ink-soft)", lineHeight: 1.55 }}>
              <b style={{ color: "var(--ink)" }}>候補の出どころ</b><br />
              一覧は「設定済 API キー ＋ 利用可能なローカルモデル」から DB が自動生成。キー未設定は <span style={{ color: "var(--warn)" }}>warn</span>（→⚙ Settings）。upscaler 等は ModelType で除外。
            </div>
          </div>

          {/* main: model rows */}
          <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderBottom: "1px solid var(--line)", flexWrap: "wrap" }}>
              <Button size="small" variant="ghost" onClick={selectAll}>全選択</Button>
              <Button size="small" variant="ghost" onClick={deselectAll}>全解除</Button>
              <Button size="small" variant="primary" onClick={selectRec}>推奨選択</Button>
              <span style={{ flex: 1 }} />
              <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>実行環境</span>
              <SegmentedControl size="small" value={env} onChange={changeEnv} options={[{ value: "all", label: "すべて" }, { value: "api", label: "APIのみ" }, { value: "local", label: "ローカルのみ" }]} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 16px", borderBottom: "1px solid var(--line)", background: "var(--paper-shade)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink)" }}>選択数: <b>{selCount}</b> {recMode && <span style={{ color: "var(--accent)" }}>(推奨)</span>}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)" }}>· ⌕ {filtered.length}件 候補（{envLabel}{atype === "all" ? "" : " / " + TYPE_LABEL[atype]}）</span>
              <span style={{ flex: 1 }} />
              <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>並び: 最終使用 ↓ · コスト · サイズ · 名前</span>
            </div>
            <div style={{ overflow: "auto", padding: "6px 10px" }}>
              {filtered.map((m) => {
                const on = selected.has(m.name);
                return (
                <div key={m.name} onClick={() => toggle(m)} style={{
                  display: "grid", gridTemplateColumns: "20px 1fr auto", gap: "var(--gap-2)", alignItems: "center",
                  padding: "8px", borderRadius: "var(--radius)", marginBottom: 4, cursor: m.disabled ? "not-allowed" : "pointer",
                  background: on ? "var(--accent-soft)" : "transparent",
                  border: "1px solid " + (on ? "var(--accent-border)" : "transparent"),
                  opacity: m.disabled ? 0.55 : 1,
                }}>
                  <span style={{ width: 14, height: 14, borderRadius: 3, border: "1px solid " + (on ? "var(--accent)" : "var(--line-strong)"), background: on ? "var(--accent)" : "var(--card)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 9 }}>{on ? "✓" : ""}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 600, textDecoration: m.disabled ? "line-through" : "none" }}>{m.name}</span>
                      <code style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-faint)" }}>{m.ver}</code>
                      <TypeBadge>{m.multi ? "multimodal" : m.types[0]}</TypeBadge>
                      <Chip kind={m.chip[0]}>{m.chip[1]}</Chip>
                    </div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)", marginTop: 2 }}>
                      {m.provider} · {m.env === "api" ? "Web API" : "ローカル"}{m.gpu ? " · GPU" : ""} · {m.types.map((t) => TYPE_LABEL[t]).join(" ")}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", minWidth: 150 }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)" }}>{m.cost}</div>
                    {m.min != null && !m.disabled && !m.needsKey ? (
                      <div style={{ marginTop: 4 }}>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)", marginBottom: 2 }}>conf min {m.min.toFixed(2)} · avg {m.avg.toFixed(2)}</div>
                        <input type="range" min="0" max="1" step="0.05" defaultValue={m.min} onClick={(e) => e.stopPropagation()} style={{ width: 140, accentColor: "var(--accent)" }} />
                      </div>
                    ) : m.needsKey ? (
                      <div style={{ fontSize: 10, color: "var(--warn)", marginTop: 4 }}>キー未設定 → ⚙ Settings</div>
                    ) : m.disabled ? (
                      <div style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 4 }}>2025-01-15 廃止 — retired</div>
                    ) : null}
                  </div>
                </div>
                );
              })}
              {filtered.length === 0 && (
                <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-faint)", padding: "16px 8px", textAlign: "center" }}>条件に一致するモデルがありません — フィルタを変更してください。</div>
              )}
            </div>

            {/* footer */}
            <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "10px 16px", borderTop: "1px solid var(--line)", background: "var(--paper-shade)" }}>
              <span style={{ fontSize: "var(--fs-small)" }}><b>{stage} に {stageSel.length} モデル選択中</b> · {stageSel.length} × 9 = {stageSel.length * 9} jobs · 全体選択 {selCount}</span>
              <span style={{ flex: 1 }} />
              <Button size="small" onClick={onClose}>キャンセル</Button>
              <Button size="small" onClick={onClose}>適用のみ</Button>
              <Button size="small" variant="primary" onClick={onClose}>適用して実行 · 9枚</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- 実行前の詳細設定（runtime pipeline options）----
function RunSettings({ staged, onClose, onRun }) {
  const { Button, Chip, TypeBadge, SegmentedControl } = DS_ANNOTATE;
  const [concurrency, setConcurrency] = React.useState("4");
  const [retries, setRetries] = React.useState("2");
  const [ratingGate, setRatingGate] = React.useState("on");
  const [overwrite, setOverwrite] = React.useState("off");
  const [dedupe, setDedupe] = React.useState("on");
  const [onFail, setOnFail] = React.useState("skip");
  const [dryRun, setDryRun] = React.useState(false);

  const Row = ({ title, sub, warn, children }) => (
    <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--gap-3)", padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--fs-small)", fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 10, color: warn ? "var(--warn)" : "var(--ink-faint)", marginTop: 2, lineHeight: 1.5 }}>{sub}</div>
      </div>
      <div style={{ flex: "none" }}>{children}</div>
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "var(--scrim)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 560, maxWidth: "94vw", maxHeight: "88vh", display: "flex", flexDirection: "column", background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-shell)", boxShadow: "var(--shadow-shell)", overflow: "hidden" }}>
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "10px 16px", background: "var(--paper-shade)", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontWeight: 600 }}>実行の詳細設定</span>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>このパイプライン実行に適用 · staged {staged}枚</span>
          <span style={{ flex: 1 }} />
          <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, color: "var(--ink-soft)" }}>✕</button>
        </div>

        {/* body */}
        <div style={{ overflow: "auto", padding: "4px 16px" }}>
          <Row title="並列実行数 concurrency" sub="同時に走らせる推論ワーカー数。多いほど速いが GPU/レート上限に注意。">
            <SegmentedControl size="small" value={concurrency} onChange={setConcurrency} options={[{ value: "1", label: "1" }, { value: "2", label: "2" }, { value: "4", label: "4" }, { value: "8", label: "8" }]} />
          </Row>
          <Row title="リトライ回数 retries" sub="失敗した推論を自動で再試行する上限回数（指数バックオフ）。">
            <SegmentedControl size="small" value={retries} onChange={setRetries} options={[{ value: "0", label: "0" }, { value: "1", label: "1" }, { value: "2", label: "2" }, { value: "3", label: "3" }]} />
          </Row>
          <Row title="失敗時の挙動 on failure" sub="リトライ上限後の扱い。skip=その画像だけ飛ばす / stop=ジョブ全体を停止。">
            <SegmentedControl size="small" value={onFail} onChange={setOnFail} options={[{ value: "skip", label: "スキップ" }, { value: "stop", label: "停止" }]} />
          </Row>
          <Row title="rating ゲート preflight" sub={ratingGate === "on" ? "X / XXX 判定の画像は annotation API に送らない（推奨）。" : "⚠ 全画像を API へ送信。NSFW がプロバイダに渡る可能性。"} warn={ratingGate === "off"}>
            <SegmentedControl size="small" value={ratingGate} onChange={setRatingGate} options={[{ value: "on", label: "ON" }, { value: "off", label: "OFF" }]} />
          </Row>
          <Row title="既存値の上書き overwrite" sub={overwrite === "off" ? "既にアノテーション済みの枠はスキップ（off）。" : "既存のタグ/スコアを新しい推論結果で上書き。"}>
            <SegmentedControl size="small" value={overwrite} onChange={setOverwrite} options={[{ value: "off", label: "OFF" }, { value: "on", label: "ON" }]} />
          </Row>
          <Row title="マルチモーダル dedupe" sub="同一モデルが複数ステージに跨る場合、推論を1回にまとめてコストを抑える。">
            <SegmentedControl size="small" value={dedupe} onChange={setDedupe} options={[{ value: "on", label: "ON" }, { value: "off", label: "OFF" }]} />
          </Row>
          <div onClick={() => setDryRun((v) => !v)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 0", cursor: "pointer" }}>
            <span style={{ width: 16, height: 16, flex: "none", borderRadius: 4, border: "1px solid " + (dryRun ? "var(--accent)" : "var(--line-strong)"), background: dryRun ? "var(--accent)" : "var(--card)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 10 }}>{dryRun ? "✓" : ""}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "var(--fs-small)", fontWeight: 600 }}>ドライラン dry-run</div>
              <div style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 2 }}>実際に推論せずジョブ件数・推定コストだけを検証する。</div>
            </div>
            {dryRun && <TypeBadge>検証のみ</TypeBadge>}
          </div>
        </div>

        {/* footer */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "10px 16px", borderTop: "1px solid var(--line)", background: "var(--paper-shade)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)" }}>並列{concurrency} · retry{retries} · {onFail} · gate {ratingGate} · overwrite {overwrite}{dryRun ? " · dry-run" : ""}</span>
          <span style={{ flex: 1 }} />
          <Button size="small" onClick={onClose}>キャンセル</Button>
          <Button size="small" onClick={onClose}>保存のみ</Button>
          <Button size="small" variant="primary" onClick={() => { onClose(); onRun && onRun(); }}>{dryRun ? "検証実行" : "保存して実行"} · {staged}枚</Button>
        </div>
      </div>
    </div>
  );
}

function AnnotateScreen({ staged, onRun }) {
  const { Card, Button, Chip, TypeBadge, SummaryStat } = DS_ANNOTATE;
  const [picker, setPicker] = React.useState(null);
  const [advanced, setAdvanced] = React.useState(false);

  const PrimaryChip = ({ name, multi, fills }) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "var(--card)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-chip)", padding: "1px 4px 1px 8px", fontSize: "var(--fs-small)", fontFamily: "var(--font-mono)" }}>
      {multi && <span style={{ fontWeight: 700, color: "var(--accent)", fontSize: 10 }}>MULTI</span>}
      {name}
      {fills && <span style={{ color: "var(--ink-faint)", fontSize: 10 }}>＋派生 {fills}</span>}
      <span style={{ color: "var(--ink-faint)", cursor: "pointer" }}>×</span>
    </span>
  );
  const DerivedChip = ({ name, from }) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, border: "1px dashed var(--line-strong)", borderRadius: "var(--radius-chip)", padding: "1px 8px", fontSize: "var(--fs-small)", fontFamily: "var(--font-mono)", fontStyle: "italic", color: "var(--ink-soft)" }}>
      ↝ {name} <span style={{ color: "var(--ink-faint)" }}>from {from}</span>
    </span>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-3)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>アノテーション — パイプライン構成</h2>
        <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>出力テーブル × ModelType で構成 · マルチモーダルは取得可能な出力を自動で全取得</span>
      </div>

      {/* presets + legend */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>preset:</span>
          <Chip kind="accent" dot="none">Default 5</Chip>
          {["Tags only 1", "Full caption 3", "Score · rate 3"].map((p) => <Chip key={p} kind="neutral" dot="none">{p}</Chip>)}
          <Button size="small" variant="ghost">+ 現状を保存</Button>
        </div>
        <div style={{ display: "flex", gap: "var(--gap-4)", flexWrap: "wrap", fontSize: 10, color: "var(--ink-soft)" }}>
          <span>凡例: <b style={{ fontFamily: "var(--font-mono)", color: "var(--accent)" }}>MULTI</b> 主割当（× で外せる）</span>
          <span><b style={{ fontFamily: "var(--font-mono)", fontStyle: "italic" }}>↝ 派生</b> = 同推論の副産物・操作不可（Results で却下）</span>
          <span>モデル候補: <b style={{ color: "var(--ink)" }}>実行環境</b>（すべて/API/ローカル）× APIキー × 各ステージの出力 で自動絞込 — <b>+ pick</b> で選択・推奨</span>
        </div>
      </Card>

      {/* stages: output table rows */}
      {STAGES.map((s) => (
        <Card key={s.key}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", flexWrap: "wrap" }}>
            <span style={{ width: 70, flex: "none", fontSize: "var(--fs-small)", fontWeight: 700, color: "var(--ink-soft)", letterSpacing: "var(--letter-caps)" }}>{s.key}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-faint)" }}>{s.n} / {s.of}</span>
            {s.models.map((m) => <PrimaryChip key={m.name} {...m} />)}
            {s.derived.map((d) => <DerivedChip key={d.name} {...d} />)}
            <Button size="small" variant="ghost" onClick={() => setPicker(s.key)}>+ pick…</Button>
            <span style={{ flex: 1 }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-soft)" }}>{s.config}</span>
          </div>
        </Card>
      ))}

      {/* preflight */}
      <Card title={<span>送信前プリフライト — OpenAI Moderations で rating 判定</span>}>
        <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", marginBottom: 8 }}>
          API へ送る画像は先に moderation で canonical rating を付与。<b style={{ color: "var(--ink)" }}>X / XXX は annotation API に送らない</b>（PG/PG-13/R は送信）。violence/graphic は R 止まり。
        </div>
        <div style={{ display: "flex", gap: "var(--gap-2)" }}>
          <Chip kind="ok">7 送信可 sendable</Chip>
          <Chip kind="warn" dot="open">2 保留 held</Chip>
          <TypeBadge>task_type=rating_preflight</TypeBadge>
        </div>
      </Card>

      {/* inference ledger */}
      <Card title="INFERENCE LEDGER" aside={<span style={{ fontWeight: 400, color: "var(--ink-soft)", fontSize: "var(--fs-small)" }}>推論回数 = ユニークモデル × 枚数（multimodal は dedupe）</span>}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--gap-3)", marginBottom: "var(--gap-3)" }}>
          <SummaryStat label="ユニークモデル" value="6" sub="local 5 · API 1 · GPU 1" />
          <SummaryStat label="× staged" value="9 枚" />
          <SummaryStat label="推論ジョブ合計" value="54" sub="3枠 → 1推論 dedupe" tone="accent" />
          <SummaryStat label="推定 est." value="~2m 40s" sub="cost ≊ $0.05 (API)" tone="info" />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {[["wd-v1-4-tagger", 9], ["wd-eva02-large-tagger", 9], ["aesthetic-v2", 9], ["musiq", 9], ["wd-rating-v2", 9]].map(([m, n]) => (
            <TypeBadge key={m}>{m} ×{n}</TypeBadge>
          ))}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--accent-hover)", background: "var(--accent-soft)", border: "1px solid var(--accent-border)", borderRadius: 3, padding: "0 6px" }}>
            <b>MULTI</b> gpt-4o-caption ×9 · 3枠→1推論
          </span>
        </div>
        <div style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 8 }}>
          + rating preflight: omni-moderation-latest × 9（X/XXX ゲート · 別 batch・課金別）。同一モデルを複数ステージに重ねても dedupe — コストは増えない。
        </div>
      </Card>

      {/* run bar */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)", padding: "var(--gap-2)", borderTop: "1px solid var(--line)" }}>
        <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", flex: 1 }}>
          scope: ステージング集合のみ · staged {staged} · 実行 → Jobs タブへ自動スイッチ
        </span>
        <Button size="small" variant="ghost" onClick={() => setAdvanced(true)}>詳細設定 ▸</Button>
        <Button variant="primary" onClick={onRun}>▶ パイプライン実行 · {staged}枚 → ⌘↵</Button>
      </div>

      {picker && <ModelPicker stage={picker} onClose={() => setPicker(null)} />}
      {advanced && <RunSettings staged={staged} onClose={() => setAdvanced(false)} onRun={onRun} />}
    </div>
  );
}

window.AnnotateScreen = AnnotateScreen;
