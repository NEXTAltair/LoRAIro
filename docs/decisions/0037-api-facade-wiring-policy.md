---
type: ADR
title: api/ Public Facade Wiring Policy
status: Accepted
timestamp: 2026-05-25
tags: []
---
# ADR 0037: api/ Public Facade Wiring Policy

- **関連 Issue**: #428(ADR 起票)、#425(調査結論)

## Context

`src/lorairo/api/` は、LoRAIro の外部向けパブリック API ファサード層として設計された。しかし現在、以下の 4 つの問題が混在している。

1. **CLI によるサブモジュールの直接インポート**:`from lorairo.public_api.batch_import import import_batch_annotations` のように、ファサードの `__init__` を経由せず内部モジュールへ直接アクセスしている。
2. **`_API_FUNCTION_MODULES` への登録漏れ**:`batch_import.import_batch_annotations` が `__init__._API_FUNCTION_MODULES` に未登録であり、遅延ロード機構の管理外になっている。
3. **スタブ実装の混入**:`annotations.annotate_images` が「0 件成功」を返すプレースホルダーのままであり、ADR 0033 が定める `AnnotationWorker` のバッチ実行契約と矛盾している。
4. **Services 層から `api/` 層への依存**:`services/image_registration_service.py` などが、`lorairo.public_api.exceptions` や `lorairo.public_api.types` をインポートしている。

## Decision

### 1. `api/` 層の役割

`api/` は、**CLI、外部スクリプト、他ツールから呼び出される外部公開 API** の配置場所とする。

```
外部呼び出し元 (CLI / スクリプト)
    → lorairo.public_api.*         ← ここを通る
        → lorairo.services.*  ← Business Logic
        → lorairo.database.*  ← Data Layer

GUI → lorairo.services.* を直接呼ぶ (api/ を経由しない)
```

- **GUI コンポーネントから `api/` を呼び出すことは禁止する**。GUI は Service 層を直接利用する。
- 例外として、`api/exceptions.py` と `api/types.py` は Service 層からのインポートを許容する。Service が送出する例外クラスや返却型の定義が `api/` に置かれているためである。

### 2. ファサード一元管理ルール

`api/` で公開する関数は、必ず `__init__._API_FUNCTION_MODULES` に登録する。

```python
_API_FUNCTION_MODULES: dict[str, tuple[str, str]] = {
    "annotate_images":             ("lorairo.public_api.annotations",  "annotate_images"),
    "import_batch_annotations":    ("lorairo.public_api.batch_import",  "import_batch_annotations"),  # 追加
    "export_dataset":              ("lorairo.public_api.export",        "export_dataset"),
    # ... (全公開関数を網羅)
}
```

- `__all__` にも対応するエントリを追加する。
- 未登録の関数は `api/` の公開 API ではなく、内部実装として扱う。

### 3. CLI のインポートパターン

CLI コマンドは、**`lorairo.public_api` のトップレベル**からインポートする。サブモジュールの直接インポートは禁止する。

```python
# 正しい
from lorairo.public_api import import_batch_annotations

# 禁止: ファサードを経由しない直接 import
from lorairo.public_api.batch_import import import_batch_annotations
```

既存の違反箇所(`cli/commands/annotate.py` の直接インポート)は、#428 の実装時に修正する。

### 4. 既存ファイルの扱い

| ファイル | 判断 | 理由 |
|---|---|---|
| `batch_import.py` | **維持+`__init__` 登録** | CLI に実際の呼び出し元が存在する。`_API_FUNCTION_MODULES` の登録漏れを修正する。 |
| `tags.py` | **維持** | CLI 向けに設計されたモジュールである。現時点で本番呼び出しがなくても、将来の CLI 拡張用として残す。 |
| `annotations.py` | **スタブとして維持(改善は別 Issue)** | ADR 0033 の `AnnotationWorker` が正規経路である。本 API はバッチキュー投入用の薄いラッパーとして再実装する予定である。 |
| `exceptions.py` | **維持** | Service 層が送出する例外定義として共有される。 |
| `types.py` | **維持** | 返却型の共有定義として Service 層からも参照される。 |

### 5. `annotations.py` と ADR 0033 の関係

`annotations.annotate_images` の現在のスタブ実装(0 件成功を返す)は、ADR 0033 の契約に反している。そのため、以下の段階方針で対処する。

- **短期**:スタブ実装に `# PENDING: #420 で AnnotationWorker へ委譲する実装に置き換え` と明記する。
- **中期**:#420 の完了後、`AnnotationWorker` へのバッチキュー投入 API として再実装する。

## Rationale

### 全関数を `__init__` で集中管理する理由

ファサードは「何が公開 API か」を 1 ファイルで宣言する役割を持つ。CLI がサブモジュールを直接インポートすると、将来のモジュール再編(`batch_import.py` のリネームなど)で CLI 側のインポートが壊れる。`__init__` を経由すれば、`_API_FUNCTION_MODULES` の書き換えだけで外部インターフェースを維持できる。

### `tags.py` を呼び出しゼロでも残す理由

本番コードからの呼び出しがないのはテスト環境の問題ではなく、現時点で CLI にタグ操作コマンドが未実装であるためである。将来 `lorairo tags list-unknown` などを CLI に追加する際の拠点として機能する。

### `annotations.py` を削除しない理由

削除すると `__all__` の `annotate_images` が参照切れとなり、テストや CI が壊れる。また、ADR 0033 の契約整備後に薄い委譲実装として再構築する予定があるため、スタブとして温存する。

## Consequences

### 良い点

- `__init__._API_FUNCTION_MODULES` が公開 API の単一リストとなり、外部公開範囲が一目で分かる。
- CLI が内部モジュールに依存しなくなり、内部再編時の影響を `__init__` だけに局所化できる。

### 悪い点

- 既存の `cli/commands/annotate.py` などで直接インポートの修正が必要になる(#428 の実装スコープ)。
- `annotations.py` のスタブが本番コードに残るため、混乱の種になり得る。これについては `PENDING` コメントで意図を明示し、#420 完了後に対処する。

## Related

- #428(実装:`api/` ファサード配線の修正)
- #425(調査:`api/` 内の呼び出しゼロ関数一覧)
- ADR 0001(Two-Tier Service Architecture — `api/` 層の位置づけ)
- ADR 0033(AnnotationWorker Batch Execution Contract — `annotations.py` との関係)
