The dark JSONL / CLI pane — the only dark surface in the app. Compose coloured tokens with the static helpers.

```jsx
<Terminal>
  <Terminal.Muted>$ lorairo-cli annotate run --json</Terminal.Muted>{"\n"}
  {"{"}<Terminal.K>"kind"</Terminal.K>:<Terminal.S>"result"</Terminal.S>,
  <Terminal.K>"count"</Terminal.K>:<Terminal.N>128</Terminal.N>,
  <Terminal.K>"has_more"</Terminal.K>:<Terminal.B>false</Terminal.B>{"}"}
</Terminal>
```
Helpers: `Terminal.K · .S · .N · .B · .Muted`.
