# ADR 0036: api/ Public Facade Wiring Policy

- **日付**: 2026-05-25
- **ステータス**: Accepted
- **関連 Issue**: #428 (ADR起票), #425 (調査結論)

## Context

`src/lorairo/api/` は LoRAIro の外部向けパブリック API ファサード層として設計された。
しかし以下の問題が混在している:

1. **CLI がサブモジュールを直接 import**: `from lorairo.api.batch_import import import_batch_annotations`
   のようにファサードの `__init__` を経由せず、内部モジュールに直接アクセスしている
2. **`_API_FUNCTION_MODULES` への登録漏れ**: `batch_import.import_batch_annotations` が
   `__init__._API_FUNCTION_MODULES` に未登録のため、遅延ロード機構の管理外になっている
3. **スタブ実装の混入**: `annotations.annotate_images` は `return 0件成功` のプレースホルダーで、
   ADR 0033 の AnnotationWorker バッチ実行コントラクトと矛盾する
4. **Services → api/ 依存**: `services/image_registration_service.py` 等が
   `lorairo.api.exceptions` / `lorairo.api.types` を import している

## Decision

### 1. api/ 層の役割

`api/` は **CLI・外部スクリプト・他ツールから呼び出される外部公開 API** の置き場とする。

```
外部呼び出し元 (CLI / スクリプト)
    → lorairo.api.*         ← ここを通る
        → lorairo.services.*  ← Business Logic
        → lorairo.database.*  ← Data Layer

GUI → lorairo.services.* を直接呼ぶ (api/ を経由しない)
```

- **GUI コンポーネントが `api/` を呼ぶのは禁止**。GUI は Service 層を直接利用する
- `api/exceptions.py` と `api/types.py` は Service 層からの import を許容する例外
  （Service が raise する例外クラス・返却型の定義が api/ に置かれているため）

### 2. ファサード一元管理ルール

`api/` で公開する関数は必ず `__init__._API_FUNCTION_MODULES` に登録する。

```python
_API_FUNCTION_MODULES: dict[str, tuple[str, str]] = {
    "annotate_images":             ("lorairo.api.annotations",  "annotate_images"),
    "import_batch_annotations":    ("lorairo.api.batch_import",  "import_batch_annotations"),  # 追加
    "export_dataset":              ("lorairo.api.export",        "export_dataset"),
    # ... (全公開関数を網羅)
}
```

- `__all__` にも対応するエントリを追加する
- 登録されていない関数は `api/` の公開 API ではなく内部実装と見なす

### 3. CLI の import パターン

CLI コマンドは **`lorairo.api` トップレベル** から import する (サブモジュール直接 import 禁止)。

```python
# 正しい
from lorairo.api import import_batch_annotations

# 禁止: ファサードを経由しない直接 import
from lorairo.api.batch_import import import_batch_annotations
```

既存の違反箇所 (`cli/commands/annotate.py` の直接 import) は #428 実装時に修正する。

### 4. 既存ファイルの扱い

| ファイル | 判断 | 理由 |
|---|---|---|
| `batch_import.py` | **維持 + __init__ 登録** | CLI に実際の呼び出し元あり。`_API_FUNCTION_MODULES` 登録漏れを修正 |
| `tags.py` | **維持** | CLI 向け意図で設計。現在の本番呼び出しゼロでも将来の CLI 拡張用 |
| `annotations.py` | **スタブとして維持、実装改善は別 Issue** | ADR 0033 の AnnotationWorker が正規パス。本 API はバッチキュー投入の薄ラッパーとして再実装予定 |
| `exceptions.py` | **維持** | Service 層が raise する例外定義として共有される |
| `types.py` | **維持** | 返却型の共有定義として Service 層からも参照される |

### 5. `annotations.py` と ADR 0033 の関係

`annotations.annotate_images` の現在のスタブ実装 (0件成功を返す) は ADR 0033 のコントラクト違反。
修正方針:
- **短期**: スタブ実装に `# PENDING: #420 で AnnotationWorker へ委譲する実装に置き換え` を明記
- **中期**: #420 完了後、AnnotationWorker のバッチキュー投入 API として再実装

## Rationale

**全関数を `__init__` に集中管理する理由**: ファサードは「何が公開 API か」を 1 ファイルで宣言する。
CLI がサブモジュールを直接 import すると、将来のモジュール再編 (batch_import.py を別名に変更等) で
CLI 側の import が壊れる。`__init__` 経由なら `_API_FUNCTION_MODULES` の書き換えだけで
外部インターフェースを維持できる。

**`tags.py` を 0呼び出しでも残す理由**: 本番呼び出しがないのはテスト環境の問題ではなく、
現時点で CLI にタグ操作コマンドがないためだけ。将来 `lorairo tags list-unknown` 等を
CLI に追加するときの拠点として機能する。

**`annotations.py` を削除しない理由**: 削除すると `__all__` の `annotate_images` が
参照切れになりテスト・CI が壊れる。また ADR 0033 のコントラクト整備後に
薄い委譲実装として復活させる予定があるため、スタブとして温存する。

## Consequences

**良い点:**
- `__init__._API_FUNCTION_MODULES` が公開 API の単一リストになり、
  「何が外部 API か」が一目でわかる
- CLI が内部モジュールに依存しなくなり、内部再編時の影響を `__init__` だけに局所化できる

**悪い点:**
- 既存の `cli/commands/annotate.py` 等に直接 import 修正が必要 (#428 実装スコープ)
- `annotations.py` のスタブが本番コードに残り続けるため、混乱の種になり得る
  → PENDING コメントで意図を明示し、#420 完了後に対処する

## Related

- #428 (実装: api/ ファサード配線修正)
- #425 (調査: api/ 呼び出しゼロ関数のリスト)
- ADR 0001 (Two-Tier Service Architecture — api/ 層の位置づけ)
- ADR 0033 (AnnotationWorker Batch Execution Contract — annotations.py との関係)
