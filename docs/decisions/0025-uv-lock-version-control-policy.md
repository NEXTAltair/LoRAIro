# ADR 0025: uv.lock Version Control Policy

- **日付**: 2026-05-14
- **ステータス**: Accepted

## Context

LoRAIro リポジトリの `.gitignore` は `uv.lock` を ignore していたため、CI checkout に lockfile が含まれず、各 CI job の `uv sync --dev` は毎回 fresh resolution を行っていた。

PR #251 で発生した CI failure がこの構造の問題を顕在化させた:

- `temporalio==1.27.2` リリース時に Linux x86_64 wheel の配布が後発だった
- `astral-sh/setup-uv@v6` の cache (`cache-dependency-glob: "pyproject.toml"`) は pyproject.toml hash を key にしているため、lockfile 非追跡では cache が古い metadata (x86_64 wheel 未公開時のもの) を保持し続ける
- 結果、`pyproject.toml` 未変更 / `uv.lock` 不在の状態で CI が同じ cache を使い続け、後から wheel が PyPI に追加されても install 失敗が継続

PyPI 上の実ファイル (`temporalio-1.27.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`) は存在するが、CI 側の uv resolver はそれを参照できなかった。

uv 公式ドキュメント (https://docs.astral.sh/uv/concepts/projects/layout/) は次のように明記している:

> "This file should be checked into version control, allowing for consistent and reproducible installations across machines."

アプリケーション・ライブラリの区別なく `uv.lock` のコミットを推奨する記述である。LoRAIro はアプリケーション (GUI + CLI ツール) であり、uv 公式推奨の前提と一致する。

## Decision

**`uv.lock` を version control に commit する** (uv 公式ベストプラクティスに従う)。

具体的に固定する事項:

1. **`.gitignore` から `uv.lock` 行を削除する。**
2. **現在の `uv.lock` を repository に commit する** (本 ADR の commit と同時)。
3. **PR で依存更新を行う場合は `pyproject.toml` と `uv.lock` を同時 commit する。** `uv lock` / `uv sync` 実行後の lockfile 変更は必ず PR に含める。
4. **CI の `uv sync --dev` 経路はそのまま使用する。** lockfile が repo に含まれる以上、uv は自動的に lock を尊重して install するため、`--frozen` フラグの追加は本 ADR では強制しない (Future enhancement)。
5. **submodule pin 更新時は `uv lock` を再実行**して `uv.lock` を更新する。submodule の依存変動が lockfile に反映される。

## Rationale

### なぜ commit するか

- **CI 安定性**: lockfile 非追跡では今回のような「upstream の wheel 配布タイミング × uv cache の古い metadata」による transient failure に晒される。lockfile 追跡で resolution を固定すれば、`pyproject.toml` が変わらない限り CI 結果は decidable。
- **開発環境の再現性**: 全開発者 / CI runner が同一バージョンを install する。submodule pin と lockfile pin がセットになるため、submodule 切替時のバージョン差異も検知できる。
- **公式推奨との整合**: uv 公式が明示的に推奨。outdated にする積極的理由がない。
- **アプリケーション性**: LoRAIro は library ではなく end-user 向けアプリケーション。「下流が pin を選ぶ」前提が成立しない (LoRAIro 自体が end of dependency chain)。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| **A. 現状維持 (`uv.lock` を ignore)** | CI の transient failure が継続する。uv 公式推奨と逆方向。 |
| **B. `astral-sh/setup-uv` の cache を無効化** | cache 復元によるセットアップ時間短縮の恩恵を失う。lockfile 追跡なしでは resolution 自体は毎回走るので根本解にならない。 |
| **C. `--refresh-package <name>` を CI で明示** | 個別 package ごとの workaround で、再発時に対応が後手に回る。lockfile 追跡なしでは資源の無駄。 |
| **D. `tool.uv.required-environments` で全環境列挙** | 環境追加ごとに pyproject.toml 修正が必要。uv 推奨は lockfile 追跡。 |

### CI cache との関係

`astral-sh/setup-uv@v6` の `cache-dependency-glob` は **キャッシュキーの再計算トリガー** に使われる。lockfile 追跡後は `cache-dependency-glob: "{pyproject.toml,uv.lock}"` に拡張すべきだが、本 ADR ではまず lockfile 追跡を成立させ、cache key の最適化は別 PR で扱う (lockfile が repo にあるだけで `uv sync` は lock を尊重するため、cache が古くても install 内容は変わらない)。

## Consequences

### 良い点

- CI failure の再発を構造的に防ぐ (lockfile 固定で resolution が decidable)
- 全開発者と CI が同一バージョンを install する保証
- submodule pin 変更時、`uv lock` を同 PR に含めることで依存変動が可視化される
- uv 公式推奨との整合

### 悪い点・トレードオフ

- **PR diff サイズが増大**: `uv.lock` (約 657KB の TOML) が repo に含まれる。依存更新 PR では大きな diff が乗る。
- **merge conflict のリスク**: 並行 PR で依存追加した場合、`uv.lock` が衝突する。`uv lock` を rebase 後に再実行して解消する運用が必要。
- **submodule pin と lock の同期義務**: submodule 更新時に `uv lock` を忘れると CI で fail する。PR template / 開発フローでガイドする。

### 運用ルール

- 依存追加 / 更新 / 削除を行う PR は **`pyproject.toml` と `uv.lock` を必ず同時 commit する**。
- `uv lock` / `uv sync` で lockfile が自動更新された場合も commit に含める。
- submodule pin (`git submodule update` 等) を更新する PR は `uv lock` を再実行する。
- `uv.lock` を rebase / merge した結果不整合になった場合は `uv lock` を再実行して再生成する。

## Related

- **Issue**: #247 (本 PR #251 で CI failure を契機に方針確立)
- **影響を受ける ADR**: 0024 (pytest test responsibility separation) — lockfile 追跡前提の CI 設計と整合
- **uv 公式ドキュメント**: https://docs.astral.sh/uv/concepts/projects/layout/
- **関連ファイル**:
  - `.gitignore` (`uv.lock` 行を削除)
  - `uv.lock` (新規 tracked)
  - `.github/workflows/ci.yml` (将来 `cache-dependency-glob` 拡張候補)
- **Future enhancement**:
  - CI `cache-dependency-glob` を `{pyproject.toml,uv.lock}` に拡張
  - 必要なら `uv sync --frozen --dev` への移行 (lockfile drift を厳密検知)
