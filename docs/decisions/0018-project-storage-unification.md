---
type: ADR
title: Project Storage Unification
status: Implemented (2026-04-25)
timestamp: 2026-04-22
tags: []
---
# ADR 0018: Project Storage Unification

## Context

LoRAIro では、GUI と CLI でプロジェクトの保存場所が**分断**していた。

### 現状の課題

1. **GUI のプロジェクト保存場所**
   - `config/lorairo.toml` の `[directories] database_base_dir = "lorairo_data"` を参照している。
   - ディレクトリ構造は `lorairo_data/<name>_<timestamp>/image_database.db` である。
   - `DirectoryService` を経由してパスを組み立てている。

2. **CLI のプロジェクト保存場所**
   - `src/lorairo/services/project_management_service.py:37` で `Path.home() / ".lorairo" / "projects"` がハードコードされている。
   - ディレクトリ構造は `~/.lorairo/projects/<name>_<timestamp>/image_database.db` である。
   - GUI 側の保存場所と完全に分離している。

3. **ユーザー体験の破綻**
   - GUI で作成したプロジェクトが CLI から見えず、逆も同様である。
   - 同じ `--project foo` を指定しても、GUI と CLI で別々の DB に接続してしまう。
   - Issue #166 で問題となった `--project` オプションのデッドコード化の一因にもなっている。

### 既存の前提

- GUI は 2025 年 10 月時点から `lorairo_data/` に大量のデータ(18k+ 画像)を蓄積している。
- CLI は比較的新しく、`~/.lorairo/projects/` の利用者は少数である。
- ADR 0009 により、CLI 環境でも Qt に依存せずサービスを利用できる設計となっている。

## Decision

**プロジェクトの保存場所を `lorairo_data/`(正確には `config/lorairo.toml` の `database_base_dir`)に統一する。**

### 具体的変更

1. `ProjectManagementService.__init__` の既定 `projects_base_dir` を以下のように変更する。

```python
# 変更前
self.projects_base_dir = projects_base_dir or (Path.home() / ".lorairo" / "projects")

# 変更後
from lorairo.utils.config import get_config
self.projects_base_dir = projects_base_dir or Path(get_config().directories.database_base_dir)
```

2. 旧 `~/.lorairo/projects/` の扱いは以下のとおりとする。
   - 自動移行は**行わない**(ユーザーがデータ配置を把握できる状態を保つため)。
   - ~~初回起動時に旧ディレクトリが存在すれば検出する。~~
   - ~~移行案内ログを INFO レベルで出力する:「旧ディレクトリが検出されました。`lorairo_data/` への移動を検討してください」~~
   - **2026-07-02 改訂**:移行案内(検出および INFO ログ)は役目を終えたため撤去した(下記の Amendment を参照)。

3. `config/lorairo.toml` のコメントを更新し、`database_base_dir` が GUI と CLI に共通のプロジェクト保存場所であることを明記する。

## Rationale

### 検討した選択肢

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A:`lorairo_data/` に統一 | GUI の既存方針に合わせる | **採用** |
| B:`~/.lorairo/projects/` に統一 | XDG ベースのユーザーローカル配置を重視する | 却下 |
| C:両方サポート(`projects` テーブルで管理) | 配置の柔軟性を重視する | 却下 |

### A を採用した理由

- **既存データの移行コストが最小**:GUI 経由で蓄積された 18k 画像の配置場所を変えずに済む。
- **設定の一元化**:`config/lorairo.toml` の `database_base_dir` が単一の真実の源泉(SSoT)になる。
- **プロジェクトの可搬性**:ユーザーホームに依存しないため、`lorairo_data/` ディレクトリごと別マシンへコピーするだけで移行できる。
- **開発環境の明示性**:`~` によるホームディレクトリの差異を避けられ、WSL・Docker・ネイティブ環境で同じ設定を使える。

### B (~/.lorairo/projects/) を却下した理由

- GUI の既存データ(18k 画像)を移行する負荷が過大である。
- ユーザーホーム配下への配置は XDG Base Directory Specification には沿うが、プロジェクト単位の可搬性が損なわれる。
- WSL 環境ではホーム配下への大量 I/O がバインドマウントのオーバーヘッドにより低速になる。

### C (両方サポート) を却下した理由

- 2 経路の整合性を維持するコストが増え、設計の複雑度が上がる。
- ユーザーが「プロジェクトがどこに保存されるか」を予測しにくくなる。
- ADR 0017 の `projects` テーブルは `path` を記録するため技術的には実現可能だが、運用上の混乱を招く。

## Consequences

### 良い点

- GUI と CLI から同じプロジェクトへアクセスできるようになる。
- `config/lorairo.toml` が単一の真実の源泉となり、設定が一元化される。
- プロジェクトディレクトリを丸ごとコピー・移動できるため、Docker ボリュームとの親和性が高い。
- 既存の GUI ユーザーへの影響がない。

### トレードオフ

- 旧 `~/.lorairo/projects/` を使っていた CLI ユーザーは手動で移行する必要がある(自動移行は行わず案内のみとする)。
- `lorairo_data/` を相対パスで指定するとカレントディレクトリに依存する(ADR 0008 の耐障害性対策で絶対パス解決を行うが、運用上の注意は必要である)。
- XDG 準拠のユーザーホーム配置を期待するユーザーからは不満が出る可能性がある。

### 軽減策

- 初回起動時の移行案内ログでユーザーへ変更を明示する。
- `lorairo_data/` の相対パス解決は `get_config().directories.database_base_dir` で一元化し、`Path.resolve()` で絶対パス化する。
- README および CHANGELOG に CLI の保存場所変更を明記する。

## Amendment (2026-07-02): 移行案内ログの撤去

Decision 2 に記載していた移行案内(旧 `~/.lorairo/projects/` の検出と INFO ログ出力)を撤去した。

- 保存場所の統一(2026-04-25 実装完了)から 2 か月以上が経過した時点で旧ディレクトリを確認したところ、残存していたのはテスト残骸(`test_project_20260422_063231`)のみであり、実プロジェクトでの利用はなかった。
- 案内ログは本来の目的である実ユーザーの移行誘導で一度も発火しておらず、恒久コードとして残す価値がない。
- 「自動移行はしない」「保存場所は `database_base_dir` に統一する」という本 ADR の核心となる決定は変更しない。

本改訂の対応 Issue は #1022(item 3)である。この撤去に伴い、Consequences に記載した「初回起動時の移行案内ログでユーザーへ変更を明示する」という軽減策も失効した。

## Related

- Issue #166(エピック):CLI `export create` リファクタリング
- Issue #1022:小粒な互換残骸の整理(移行案内ログ撤去の Amendment)
- Issue #177 [F]:本 ADR を実装するサブ Issue(`ProjectManagementService` 改修)
- ADR 0008: CLAUDE.md Resilience Architecture(絶対パス解決)
- ADR 0009: Qt Decoupling Design(CLI 環境でのサービス独立性)
- ADR 0017: Project DB Normalization(`projects.path` カラムがこの統一と整合)
