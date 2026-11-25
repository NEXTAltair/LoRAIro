---
type: ADR
title: uv.lock Version Control Policy
status: Accepted
timestamp: 2026-05-14
tags: []
---
# ADR 0025: uv.lock Version Control Policy

## Context

LoRAIro リポジトリの `.gitignore` では `uv.lock` を除外対象にしていた。そのため、CI のチェックアウトにロックファイルが含まれず、各 CI ジョブの `uv sync --dev` が毎回依存関係を一から解決していた。

PR #251 で発生した CI 失敗により、この構造の問題が顕在化した。

- `temporalio==1.27.2` のリリース時、Linux x86_64 向け wheel の配布が後発になった。
- `astral-sh/setup-uv@v6` のキャッシュ(`cache-dependency-glob: "pyproject.toml"`)は `pyproject.toml` のハッシュをキーとしている。ロックファイルが未追跡の状態では、キャッシュが古いメタデータ(x86_64 wheel 未公開時の情報)を保持し続ける。
- 結果として、`pyproject.toml` が未変更かつ `uv.lock` が不在の状態で CI が同一キャッシュを使い続け、後から wheel が PyPI に追加されてもインストール失敗が解消しなかった。

PyPI 上には実ファイル(`temporalio-1.27.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`)が存在していたにもかかわらず、CI 側の uv リゾルバーはそれを参照できなかったのである。

uv 公式ドキュメント(https://docs.astral.sh/uv/concepts/projects/layout/)は次のように明記している。

> "This file should be checked into version control, allowing for consistent and reproducible installations across machines."

アプリケーションとライブラリの区別なく `uv.lock` のコミットを推奨する記述である。LoRAIro は GUI と CLI を備えたアプリケーションであり、uv 公式推奨の前提と完全に一致する。

## Decision

**`uv.lock` をバージョン管理にコミットする**(uv 公式のベストプラクティスに従う)。

具体的な固定事項は以下のとおりである。

1. **`.gitignore` から `uv.lock` の行を削除する。**
2. **現在の `uv.lock` をリポジトリにコミットする**(本 ADR のコミットと同時)。
3. **PR で依存を更新する場合は、`pyproject.toml` と `uv.lock` を同時にコミットする。** `uv lock` や `uv sync` の実行後に生じたロックファイルの変更は、必ず PR に含める。
4. **CI の `uv sync --dev` 経路はそのまま使用する。** ロックファイルがリポジトリに含まれる以上、uv は自動的にロックを尊重してインストールする。`--frozen` フラグの追加は本 ADR では強制せず、将来の拡張候補とする。
5. **サブモジュールのピンを更新する際は `uv lock` を再実行して `uv.lock` を更新する。** これにより、サブモジュール側の依存変動がロックファイルへ確実に反映される。

## Rationale

### なぜコミットするか

- **CI の安定性**: ロックファイルが未追跡のままだと、今回のような「上流の wheel 配布タイミングと uv キャッシュの古いメタデータの食い違い」による一時的失敗に晒される。ロックファイルを追跡して依存解決を固定すれば、`pyproject.toml` が変わらない限り CI 結果は決定的になる。
- **開発環境の再現性**: 全開発者と CI ランナーが同一バージョンをインストールできる。サブモジュールのピンとロックファイルのピンが組になるため、サブモジュール切り替え時のバージョン差異も検知しやすくなる。
- **公式推奨との整合**: uv 公式が明示的にコミットを推奨しており、追跡しない積極的な理由がない。
- **アプリケーションとしての性質**: LoRAIro はライブラリではなくエンドユーザー向けアプリケーションであり、依存チェーンの末端に位置する。「下流パッケージがピンを選ぶ」という前提は成立しない。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| **A. 現状維持(`uv.lock` を除外)** | CI の一時的失敗が継続し、uv 公式推奨にも反する。 |
| **B. `astral-sh/setup-uv` のキャッシュを無効化する** | キャッシュ復元によるセットアップ時間短縮の恩恵を失う。ロックファイル追跡なしでは毎回依存解決が走るため根本解にならない。 |
| **C. `--refresh-package <name>` を CI で明示する** | 個別パッケージごとの対症療法であり、再発時の対応が後手に回る。ロックファイル追跡なしでは資源の無駄になる。 |
| **D. `tool.uv.required-environments` で全環境を列挙する** | 環境追加のたびに `pyproject.toml` の修正が必要になる。uv の推奨はロックファイルの追跡である。 |

### CI キャッシュとの関係

`astral-sh/setup-uv@v6` の `cache-dependency-glob` は、キャッシュキーの再計算トリガーとして使われる。ロックファイル追跡後は `cache-dependency-glob: "{pyproject.toml,uv.lock}"` へ拡張すべきである。ただし本 ADR ではまずロックファイル追跡の成立を優先し、キャッシュキーの最適化は別 PR で扱う。ロックファイルがリポジトリにあれば `uv sync` はロックを尊重するため、キャッシュが古くてもインストール内容は変わらない。

## Consequences

### 良い点

- ロックファイル固定により依存解決が決定的になり、CI 失敗の再発を構造的に防げる。
- 全開発者と CI が同一バージョンをインストールする保証が得られる。
- サブモジュールのピン変更時に `uv lock` を同 PR へ含めることで、依存変動が可視化される。
- uv 公式の推奨運用と整合する。

### 悪い点・トレードオフ

- **PR の差分サイズが増大する**: `uv.lock`(約 657KB の TOML)がリポジトリに含まれるため、依存更新 PR の差分が大きくなる。
- **マージコンフリクトのリスク**: 並行する PR で依存を追加すると `uv.lock` が衝突する。リベース後に `uv lock` を再実行して解消する運用が必要になる。
- **サブモジュールピンとロックの同期義務**: サブモジュール更新時に `uv lock` を忘れると CI が失敗する。PR テンプレートや開発フローで手順を案内する。

### 運用ルール

- 依存の追加・更新・削除を行う PR では、**`pyproject.toml` と `uv.lock` を必ず同時にコミットする**。
- `uv lock` や `uv sync` でロックファイルが自動更新された場合もコミットに含める。
- サブモジュールのピン(`git submodule update` 等)を更新する PR では `uv lock` を再実行する。
- リベースやマージで `uv.lock` が不整合になった場合は、`uv lock` を再実行して再生成する。

## Related

- **Issue**: #247(PR #251 の CI 失敗を契機に方針を確立)
- **影響を受ける ADR**: 0024(pytest Test Responsibility Separation by Package)— ロックファイル追跡前提の CI 設計と整合
- **uv 公式ドキュメント**: https://docs.astral.sh/uv/concepts/projects/layout/
- **関連ファイル**:
  - `.gitignore`(`uv.lock` 行を削除)
  - `uv.lock`(新規追跡対象)
  - `.github/workflows/ci.yml`(将来 `cache-dependency-glob` 拡張候補)
- **将来の拡張候補**:
  - CI の `cache-dependency-glob` を `{pyproject.toml,uv.lock}` に拡張する
  - 必要に応じて `uv sync --frozen --dev` へ移行し、ロックファイルの乖離を厳密に検知する
