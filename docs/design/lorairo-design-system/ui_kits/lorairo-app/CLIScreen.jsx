// CLIScreen — the agent-friendly CLI contract (JSONL / stderr split, kinds, errors).
const DS_CLI = window.LoRAIroDesignSystem_64d8f7;

function CLIScreen() {
  const { Card, TypeBadge, Chip, Terminal } = DS_CLI;
  const T = Terminal;

  const adrs = [["ADR 0057", "JSONL / error"], ["ADR 0058", "output mode"], ["ADR 0059", "introspection"], ["ADR 0060", "pagination"]];
  const kinds = [
    { k: "item", tone: "info", desc: "ストリーム要素 — 1 件ごとの結果" },
    { k: "result", tone: "ok", desc: "終端サマリ — count / has_more" },
    { k: "error", tone: "err", desc: "構造化エラー — code / exit" },
  ];
  const cmds = [["annotate", 2], ["batch", 6], ["export", 1], ["images", 3], ["models", 2], ["project", 3]];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-3)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-3)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>CLI — agent-friendly contract</h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>lorairo-cli · 6 groups · 17 subcommands</span>
      </div>

      <Card title="機械可読契約レイヤー a contract layer over the existing CLI">
        <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", lineHeight: 1.7, marginBottom: "var(--gap-2)" }}>
          Typer + rich の既存 CLI に契約を移植。stdout は JSONL（1 行 = 1 JSON object）、stderr はログ・進捗。失敗も最終行に構造化エラーを出すのでエージェントが安定して driving できる。
        </div>
        <div style={{ display: "flex", gap: "var(--gap-2)", flexWrap: "wrap" }}>
          {adrs.map(([a, d]) => <TypeBadge key={a}>{a} · {d}</TypeBadge>)}
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--gap-3)", alignItems: "start" }}>
        <Card title="stdout = JSONL">
          <Terminal>
            <T.Muted>$ lorairo-cli annotate run --models wd-eva02 --json</T.Muted>{"\n"}
            {"{"}<T.K>"kind"</T.K>:<T.S>"item"</T.S>,<T.K>"image_id"</T.K>:<T.N>42</T.N>,<T.K>"tags"</T.K>:[<T.S>"1girl"</T.S>]{"}"}{"\n"}
            {"{"}<T.K>"kind"</T.K>:<T.S>"item"</T.S>,<T.K>"image_id"</T.K>:<T.N>43</T.N>,<T.K>"tags"</T.K>:[<T.S>"solo"</T.S>]{"}"}{"\n"}
            {"{"}<T.K>"kind"</T.K>:<T.S>"result"</T.S>,<T.K>"count"</T.K>:<T.N>128</T.N>,<T.K>"has_more"</T.K>:<T.B>false</T.B>{"}"}
          </Terminal>
        </Card>
        <Card title="stderr = ログ・進捗 / 構造化エラー">
          <Terminal>
            <T.Muted>[i] resolving models… 3 ready</T.Muted>{"\n"}
            <T.Muted>[!] gpt-5-mini: needs key — skipped</T.Muted>{"\n"}
            {"{"}<T.K>"kind"</T.K>:<T.S>"error"</T.S>,<T.K>"code"</T.K>:<T.S>"RATE_LIMITED"</T.S>,<T.K>"exit"</T.K>:<T.N>1</T.N>{"}"}
          </Terminal>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--gap-3)", alignItems: "start" }}>
        <Card title="3 つの kind">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-2)" }}>
            {kinds.map((k) => (
              <div key={k.k} style={{ display: "flex", alignItems: "center", gap: "var(--gap-2)" }}>
                <Chip kind={k.tone} dot="none"><code style={{ fontFamily: "var(--font-mono)" }}>{k.k}</code></Chip>
                <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)" }}>{k.desc}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "var(--gap-2)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>
            出力モード: --json › env LORAIRO_CLI_JSON › 既定 rich · exit 0/2/1
          </div>
        </Card>
        <Card title="コマンド総覧 17 subcommands">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px" }}>
            {cmds.map(([c, n]) => (
              <div key={c} style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--fs-small)" }}>
                <code style={{ fontFamily: "var(--font-mono)" }}>{c}</code>
                <span style={{ color: "var(--ink-soft)" }}>{n}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "var(--gap-2)", fontSize: "var(--fs-small)", color: "var(--ink-faint)" }}>
            + top-level version / status / list-commands / describe
          </div>
        </Card>
      </div>
    </div>
  );
}

window.CLIScreen = CLIScreen;
