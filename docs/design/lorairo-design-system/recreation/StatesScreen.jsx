// FRAME 9 · STATES — scale & empty-state catalogue. Shows how the same
// screens flex at 0 / empty / clean / idle / 500 / 9k / edge. DS primitives only.
const DS_STATES = window.LoRAIroDesignSystem_64d8f7;

function StatesScreen() {
  const { Card, Button, Chip, ProgressBar } = DS_STATES;

  const StCard = ({ where, title, note, children }) => (
    <Card
      title={<span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "var(--letter-caps)", textTransform: "uppercase", background: "var(--ink)", color: "var(--paper)", borderRadius: "var(--radius-badge)", padding: "1px 7px" }}>{where}</span>
        <span style={{ fontSize: "var(--fs-small)", fontWeight: 600, color: "var(--ink)" }}>{title}</span>
      </span>}
      bodyStyle={{ display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}
    >
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}>{children}</div>
      <div style={{ marginTop: "auto", borderTop: "1px dashed var(--line)", paddingTop: 8, fontSize: "10px", color: "var(--ink-faint)", lineHeight: 1.5 }}>{note}</div>
    </Card>
  );

  const Empty = ({ glyph, gcolor, head, hcolor, desc, actions }) => (
    <div style={{ textAlign: "center", padding: "10px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 30, color: gcolor || "var(--ink-faint)", fontFamily: "var(--font-mono)", lineHeight: 1 }}>{glyph}</span>
      <span style={{ fontSize: "var(--fs-base)", fontWeight: 700, color: hcolor || "var(--ink)" }}>{head}</span>
      <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", lineHeight: 1.55, maxWidth: 280 }}>{desc}</span>
      {actions && <div style={{ display: "flex", gap: "var(--gap-2)", flexWrap: "wrap", justifyContent: "center", marginTop: 4 }}>{actions}</div>}
    </div>
  );

  const TokHit = ({ tk, w, n, zero }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", width: 96, color: zero ? "var(--err)" : "var(--ink)" }}>{tk}</span>
      <div style={{ flex: 1 }}><ProgressBar value={w} tone="info" /></div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-soft)", width: 48, textAlign: "right" }}>{n}</span>
    </div>
  );

  const Pattern = ({ label, count, action, accent }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, border: "1px solid " + (accent ? "var(--accent)" : "var(--line)"), background: accent ? "var(--accent-soft)" : "var(--paper-shade)", borderRadius: "var(--radius)", padding: "6px 10px" }}>
      {accent ? <span style={{ color: "var(--accent)" }}>⌕</span> : <Chip kind="warn" dot="open" style={{ padding: "0 6px" }}>warn</Chip>}
      <span style={{ flex: 1, fontSize: "var(--fs-small)", color: "var(--ink)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700, color: accent ? "var(--accent)" : "var(--ink)", background: "var(--card)", borderRadius: "var(--radius-badge)", padding: "1px 7px", border: "1px solid var(--line)" }}>{count}</span>
      {action && <span style={{ fontSize: "10px", color: "var(--accent)", borderBottom: "1px dashed var(--accent)", cursor: "pointer" }}>{action}</span>}
    </div>
  );

  const Skel = () => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
      <span style={{ width: 26, height: 26, flex: "none", background: "var(--paper-shade)", borderRadius: "var(--radius)" }} />
      <span style={{ flex: 2, height: 9, background: "var(--paper-shade)", borderRadius: 3 }} />
      <span style={{ flex: 1, height: 9, background: "var(--paper-shade)", borderRadius: 3 }} />
      <span style={{ flex: 1, height: 9, background: "var(--paper-shade)", borderRadius: 3 }} />
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-3)", marginBottom: "var(--gap-3)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>状態カタログ</h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>同じ画面が規模と状況でどう変わるか — scale &amp; empty states</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(360px,1fr))", gap: "var(--gap-3)", alignItems: "stretch" }}>
        {/* A · SEARCH 0 hit */}
        <StCard where="Search" title="0 hit — 矛盾フィルタの診断"
          note="0 hit を行き止まりにしない: どれを外せば何件になるかまで提示（単独 hit 数は事前計算済）">
          <Empty glyph="⌀" head="0 matches — クエリが矛盾しています"
            desc={<span>単独ではヒットする条件の <b style={{ color: "var(--err)" }}>交差が 0</b>。犯人はトークン別 hit 数で見える:</span>} />
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <TokHit tk="1girl" w={67} n="8,420" />
            <TokHit tk={"\"桜の下\""} w={4} n="412" />
            <TokHit tk="w≥1024" w={26} n="3,210" zero />
            <TokHit tk="portrait 厳密" w={47} n="5,930" zero />
          </div>
          <div style={{ display: "flex", gap: "var(--gap-2)", flexWrap: "wrap" }}>
            <Button size="small">最後の条件を外す</Button>
            <Button size="small" variant="ghost">w≥1024 を外す → 1,840 hit</Button>
          </div>
        </StCard>

        {/* B · RESULTS never ran */}
        <StCard where="Results" title="バッチ未実行 — 初回の空"
          note="空画面は次の1アクションへの案内板。機能説明の長文は置かない">
          <Empty glyph="▸" head="まだ結果がありません"
            desc="Annotate でパイプラインを実行すると、完了と同時にここへ自動で届きます（品質トリアージ）"
            actions={<React.Fragment>
              <Button size="small" variant="primary">▶ Annotate でパイプラインを組む</Button>
              <Button size="small" variant="ghost">過去の実行履歴 17件 → Jobs</Button>
            </React.Fragment>} />
        </StCard>

        {/* C · RESULTS 0 issues */}
        <StCard where="Results" title="issues 0 — clean バッチ"
          note="「問題ないものは触らない」の終着点 — clean は祝って素通りさせる。行リストは畳んで残す">
          <Empty glyph="✓" gcolor="var(--ok)" hcolor="var(--ok)" head="0 issues — 9 / 9 clean"
            desc="構造的チェック5種（空タグ・no-score・unknown tier・rating不一致・scorer不一致）すべて通過。閾値ベースの煽りは無し"
            actions={<React.Fragment>
              <Button size="small" variant="primary">そのまま Export へ · 9枚</Button>
              <Button size="small" variant="ghost">▸ 9行を展開</Button>
            </React.Fragment>} />
        </StCard>

        {/* D · JOBS idle */}
        <StCard where="Jobs" title="空 — 実行もキューもなし"
          note="空でも履歴テーブルは消さない — Jobs の半分は「過去に何が走ったか」の台帳。サマリ帯は畳む">
          <Empty glyph="◇" head="実行中・キュー・非同期バッチ なし"
            desc={<span style={{ fontFamily: "var(--font-mono)" }}>直近: 14:32 既定パイプライン <b style={{ color: "var(--ok)" }}>✓ 54 outputs</b> → <span style={{ color: "var(--accent)" }}>Results</span></span>}
            actions={<Button size="small" variant="primary">▶ Annotate から実行</Button>} />
        </StCard>

        {/* E · RESULTS @ 500 */}
        <StCard where="Results · 500" title="日常上限 — 仮想スクロール + 同種畳み"
          note="500 = ステージング上限。行は仮想化、issue は同種を1カードに集約。ページングはしない">
          <div style={{ display: "flex", gap: "var(--gap-2)", flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 150 }}><Pattern label="low-conf tags" count="×37" /></div>
            <div style={{ flex: 1, minWidth: 150 }}><Pattern label="short caption" count="×12" /></div>
          </div>
          <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--ink-soft)", background: "var(--paper-shade)", padding: "4px 8px", borderBottom: "1px solid var(--line)" }}>行 1–18 / 500 を描画（virtual scroll）· 残りはスクロールで実体化</div>
            <div style={{ padding: "2px 8px" }}>{[0, 1, 2, 3, 4].map((i) => <Skel key={i} />)}</div>
          </div>
        </StCard>

        {/* F · RESULTS @ 9k */}
        <StCard where="Results · 9k" title="本気の LoRA セット — per-row 非表示"
          note="個別確認は pattern → Search へ絞り込みを受け渡す（issue → query 変換）。Results は集約監視盤に">
          <Pattern label="tag flood（>200 tags/img）" count="×112" action="→ Search で開く" />
          <Pattern label="rating 競合（モデル間不一致）" count="×287" action="→ Search で開く" />
          <Pattern label="空タグ（推論失敗ではない0件）" count="×34" action="→ Search で開く" />
          <Pattern label={<span><b>clean</b> 8,567 / 9,000（無 flag）— 抜き取り監査</span>} count="上限30" action="→ 層化30枚を抜き取り" accent />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>9,000 行のリストは描画しない — patterns（集約 issue）だけを出す</span>
        </StCard>

        {/* G · CLEAN AUDIT edge */}
        <StCard where="Clean 監査" title="端状態 — 抜き取りの境界"
          note="OK箱は flag を増やす装置ではなく、flag されなかった集合を抜き取る装置。母数で見せ方だけ変える（規則は1つ）">
          {[
            ["clean 0 — 全部 flagged", "抜き取りバンドは出さない。監査すべき「見ていない集合」が存在しないため。脱 flagged したらバンドが現れる"],
            ["clean 1 — 抜き取り不要", "母数1 ＝ サンプルは全数。「1/1 を確認」だけを表示し、re-sample は無効化"],
            ["小母数（n≤20）= 全数抜き取り", "サンプリングせず clean を全部見せる。⌈√n⌉・上限30 は n≥21 で初めて効く — 規則は1つ"],
          ].map(([h, d]) => (
            <div key={h} style={{ border: "1px solid var(--line)", borderLeft: "3px solid var(--accent)", borderRadius: "var(--radius)", background: "var(--card)", padding: "6px 10px" }}>
              <div style={{ fontSize: "var(--fs-small)", fontWeight: 600, color: "var(--ink)" }}>{h}</div>
              <div style={{ fontSize: "10px", color: "var(--ink-soft)", lineHeight: 1.5, marginTop: 2 }}>{d}</div>
            </div>
          ))}
        </StCard>
      </div>
    </div>
  );
}

window.StatesScreen = StatesScreen;
