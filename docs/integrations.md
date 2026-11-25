---
type: Guide
title: 外部パッケージ統合
status: Accepted
timestamp: 2026-06-26
tags: [annotation, tag-normalization]
depends_on: [transformers, litellm, pydanticai]
---
# 外部パッケージ統合

## 概要

LoRAIro は 2 つのローカルパッケージを統合し、タグ管理と AI アノテーションの機能を提供する。

- `local_packages/genai-tag-db-tools` — タグデータベース管理
- `local_packages/image-annotator-lib` — マルチプロバイダー AI アノテーション

両パッケージは `uv.sources` で editable インストールされ、プロジェクトルートの `.venv` を共有する。

## genai-tag-db-tools 統合

### 目的

画像タグの正規化、検索、登録を外部タグデータベース(User DB と Base DB)で管理する。

### 統合ポイント

#### 主要エントリーポイント

**対象ファイル**: `src/lorairo/database/repository/annotation_record.py`

```python
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
```

- タグ検索: `search_tags(TagSearchRequest(...))`
- タグ登録: `TagRegisterService.register_tag(TagRegisterRequest(...))`
- タグ読み込み: User DB と Base DB を統合検索する `MergedTagReader`

#### サービス層

**対象ファイル**: `src/lorairo/services/tag_management_service.py`

```python
from genai_tag_db_tools.db.repository import TagReader  # User DB only
from genai_tag_db_tools.models import TagTypeUpdate
```

**責務**:
- User DB 専用のタグ管理(Base DB は対象外)
- `unknown` タイプタグの検索と一括更新
- タイプ名一覧の取得

#### GUI 層

**対象ファイル**: `src/lorairo/gui/widgets/tag_management_widget.py`

**主な機能**:
- `unknown` タイプタグの一覧表示
- タイプ選択 UI
- 一括タイプ更新

### 公開 API の使用方法

#### タグ検索

```python
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.models import TagSearchRequest

request = TagSearchRequest(
    tag_string="1girl, blue eyes",
    format_name="Lorairo",  # Optional filter
    search_type="partial"    # "exact" or "partial"
)
results = search_tags(request)
```

一致したタグを含む `TagSearchResponse` を返す。

#### タグ登録

```python
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.models import TagRegisterRequest

service = TagRegisterService()
request = TagRegisterRequest(
    tag_name="blue eyes",
    format_name="Lorairo",
    type_name="unknown"  # Placeholder until user assigns type
)
result = service.register_tag(request)
```

基本フローは「検索 → 登録 → 競合時リトライ」である。競合時は以下のように扱う。

- `format_id` の衝突: フォーマットスコープ内で自動インクリメントする
- 重複タグ: 既存の `tag_id` を返す

### データベースアーキテクチャ

#### User DB(主)

既定の配置先は `HF_HOME/.cache/genai-tag-db-tools/user_db.sqlite` である。

```python
from genai_tag_db_tools.db.core import init_user_db

init_user_db(user_db_dir="path/to/user_db")  # Auto-created if not exists
```

**運用方針**:
- **自動生成**: LoRAIro 起動時に自動で初期化する
- **`format_id` 範囲**: 1000 以上を User DB 専用として予約する
- **`type_name` 既定値**: プレースホルダーとして `"unknown"` を設定する
- **分離**: ユーザーが登録したタグのみを格納する

#### Base DB(オプション)

HuggingFace からダウンロードする 3 つの DB ファイルで構成される。

- 整備済みのタグ分類体系と複数フォーマットの事前登録タグを含む
- LoRAIro からは読み取り専用として扱う

User DB と Base DB を横断検索する場合は `MergedTagReader` を使用する。

```python
from genai_tag_db_tools.db.repository import MergedTagReader

reader = MergedTagReader()  # Combines User DB + Base DB
tags = reader.search_tags("blue eyes")  # Searches both DBs
```

### format_id の衝突回避

User DB と Base DB の間で `format_id`(1–999)が重複する恐れがあるため、User DB には 1000 以上を予約している。

```python
# In genai-tag-db-tools/services/tag_register.py
def _get_or_create_format_id(format_name: str) -> int:
    existing = db.query_format_id(format_name)
    if existing:
        return existing

    # Auto-increment from 1000
    max_id = db.get_max_format_id() or 999
    return max(max_id + 1, 1000)
```

これにより、User DB(1000 以上)と Base DB(1–999)の衝突を防ぎ、フォーマット単位の自動採番と安全な並行登録を実現している。

### タグタイプ管理

#### タイプ選択戦略

既定値は `type_name="unknown"` である。ユーザーによる分類は以下の手順で行う。

1. `TagManagementService.get_unknown_tags()` で未分類タグを一覧取得する
2. `TagManagementService.get_all_available_types()` で利用可能なタイプ一覧を取得する
3. `TagManagementService.update_tag_types(tag_ids, new_type)` で一括更新する

**主なタイプ名の例**:
- `character`: キャラクター名
- `copyright`: 作品名・シリーズ名
- `general`: 一般的な描写タグ
- `meta`: メタデータタグ
- `unknown`: 未分類(プレースホルダー)

#### 一括更新 API

```python
from genai_tag_db_tools.models import TagTypeUpdate

updates = [
    TagTypeUpdate(tag_id=1, type_name="character"),
    TagTypeUpdate(tag_id=2, type_name="general")
]

service.update_tags_type_batch(updates, format_name="Lorairo")
```

更新はアトミックに実行され、全件成功するかロールバックされる。

### 統合テスト

タグ統合コードのカバレッジ目標は 75% 以上とする。

```python
def test_tag_registration(tmp_path):
    # Initialize User DB in temp location
    user_db_path = tmp_path / "user_db.sqlite"
    init_user_db(user_db_dir=user_db_path.parent)

    # Register tag
    service = TagRegisterService()
    request = TagRegisterRequest(
        tag_name="test_tag",
        format_name="Lorairo",
        type_name="unknown"
    )
    result = service.register_tag(request)

    assert result.tag_id > 0
    assert result.format_id >= 1000  # User DB range
```

## image-annotator-lib 統合

### 目的

OpenAI、Anthropic、Google、およびローカルモデルによるマルチプロバイダーの画像キャプション生成とタグ付けを提供する。

### 統合ポイント

#### 主要アダプター

**対象ファイル**: `src/lorairo/annotation/annotator_adapter.py`

```python
from image_annotator_lib import get_available_annotators, create_annotator
from image_annotator_lib.types import AnnotationResult, AnnotatorConfig
```

**責務**:
- プロバイダーの選択と設定
- アノテーターインスタンスの生成
- 結果型の変換

#### アノテーションロジック

**対象ファイル**: `src/lorairo/annotation/annotation_runner.py`

```python
from image_annotator_lib import annotate
from image_annotator_lib.types import AnnotationRequest
```

**責務**:
- アノテーションリクエストの構築
- バッチ処理の調整
- エラーハンドリングとリトライ制御

#### サービス層

**対象ファイル**: `src/lorairo/annotation/annotator_adapter.py`

**責務**:
- アノテーション用ビジネスロジックのラップ
- 設定サービスとの連携
- 結果の集約

#### ワーカー層

**対象ファイル**: `src/lorairo/gui/workers/annotation_worker.py`

**責務**:
- Qt ベースの非同期アノテーション実行
- Signal を介した進捗報告
- GUI への結果引き渡し

### プロバイダー設定

#### 設定ファイル

**対象ファイル**: `config/lorairo.toml`

```toml
[api]
openai_key = "sk-..."
claude_key = "sk-ant-..."
google_key = "..."

[annotation]
provider = "openai"  # or "anthropic", "google", "local"
model = "gpt-4o"
temperature = 0.7
max_tokens = 1000
```

#### プロバイダー選択

```python
from lorairo.annotation.annotator_adapter import AnnotatorLibraryAdapter

adapter = AnnotatorLibraryAdapter(config_service)
annotator = adapter.create_annotator(
    provider="openai",
    model="gpt-4o",
    api_key=config.get_openai_key()
)
```

### アノテーションワークフロー

#### 単一画像アノテーション

```python
from image_annotator_lib import annotate
from image_annotator_lib.types import AnnotationRequest

request = AnnotationRequest(
    image_path="path/to/image.jpg",
    provider="openai",
    model="gpt-4o",
    prompt="Describe this image in detail"
)

result = annotate(request)
# result.caption: str
# result.tags: list[str]
# result.confidence: float
```

#### バッチアノテーション

複数画像および複数モデルの同期アノテーションでは、`annotate()` に画像リストとモデルリストをまとめて渡す。戻り値は pHash をキーとする辞書 `PHashAnnotationResults` である。

```python
from lorairo.annotation.annotator_adapter import AnnotatorLibraryAdapter

adapter = AnnotatorLibraryAdapter(config_service)
results = adapter.annotate(
    images=[image1, image2],  # PIL.Image のリスト
    litellm_model_ids=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
    phash_list=None,  # 省略時はライブラリ内部で自動計算
)
```

#### Provider Batch API

Provider Batch API は、同期 `annotate_batch()` とは独立した非同期ジョブライフサイクルである。OpenAI と Anthropic の direct 経路におけるプロバイダー固有ペイロードの作成、送信、取得、キャンセル、結果取得、解析、正規化結果の生成は `image-annotator-lib` が担う。

LoRAIro は `provider_batch_jobs`、`provider_batch_items`、`provider_batch_artifacts` の 3 テーブルでジョブ・アイテム・成果物の状態を管理する。ライブラリから返る `BatchFetchResult` は既存のアノテーション保存経路へ取り込み、結果照合の SSoT には `custom_id = img-{image_id}` を用いる。

**実装ステータス(2026-05-27 時点)**:
- **Anthropic direct 経路**: 完全実装(ライブラリ側 `webapi/batch/adapters/anthropic.py` と LoRAIro の CLI・GUI・サービス・DB)
- **OpenAI direct 経路**: `/v1/moderations` による rating preflight batch のみ実装。通常のアノテーション生成バッチは未対応
- **Google Vertex AI**: ADR 0038 Phase 3 の対象であり、CLI・GUI ともに送信を拒否する
- **OpenRouter 経路**: ADR 0038 の対象外(non-goal)であり、CLI・GUI ともに送信を拒否する

利用条件、CLI・GUI の運用手順、ステータスマッピング、プライバシー警告、ADR と実装の差分は [Provider Batch API 利用条件と運用ガイド](provider-batch-api.md) を参照する。

### データ型

#### PHashAnnotationResults

```python
{
    "image_path": "path/to/image.jpg",
    "phash": "abc123...",  # Perceptual hash
    "caption": "A detailed description...",
    "tags": ["tag1", "tag2", ...],
    "provider": "openai",
    "model": "gpt-4o",
    "confidence": 0.95,
    "timestamp": "2025-01-01T12:00:00Z"
}
```

**用途**:
- pHash をキーとしてデータベースへ保存する
- pHash の照合により重複画像を検出する
- モデル・プロバイダーごとにアノテーション結果を管理する

### エラーハンドリング

#### エラートリアージ(自動リトライなし、ADR 0033)

LoRAIro はアノテーションエラーを自動リトライしない設計を採用している(ADR 0033)。`annotate()` の結果に含まれる `retryable` フラグはエラーレコードへ保存する。

`ErrorTriageService`(`src/lorairo/services/error_triage_service.py`)は `(operation_type, error_type, model_name)` 単位で同一原因をグルーピングし、サマリとフィルタリングを提供する。ユーザーは Errors タブでエラーを確認し、必要に応じて条件を修正して別ジョブとして再送信する。タブ上の操作は resolve と bulk resolve に限定している。

```python
from lorairo.services.error_triage_service import ErrorTriageService

triage = ErrorTriageService()
summary = triage.summarize(rows)  # ErrorRow のリストを同一原因でグルーピングしたサマリを返す
```

#### フォールバックチェーン

```python
providers = ["openai", "anthropic", "google"]
for provider in providers:
    try:
        result = annotate(image, provider=provider)
        break
    except ProviderError:
        continue  # Try next provider
```

### テスト戦略

#### 外部 API のモック

```python
import pytest
from unittest.mock import patch

@patch('image_annotator_lib.annotate')
def test_annotation_service(mock_annotate):
    mock_annotate.return_value = AnnotationResult(
        caption="Test caption",
        tags=["test"],
        confidence=1.0
    )

    service = AnnotatorLibraryAdapter(config)
    result = service.annotate("image.jpg")

    assert result.caption == "Test caption"
```

#### 統合テスト

実際の API を呼び出すテストには `@pytest.mark.integration` を付与する。

```python
@pytest.mark.integration
def test_openai_annotation_real():
    # Uses real OpenAI API (requires API key)
    result = annotate(
        image_path="tests/resources/test_image.jpg",
        provider="openai",
        model="gpt-4o"
    )
    assert len(result.caption) > 0
```

## 統合メンテナンス

### バージョン互換性

- **genai-tag-db-tools**: 最小バージョン 0.3.0(公開 API 対応)、推奨は最新版(性能改善)
- **image-annotator-lib**: 最小バージョン 0.2.0(マルチプロバイダー対応)、推奨は最新版(新規プロバイダー対応)

### 更新手順

1. `pyproject.toml` を更新する。
   ```toml
   [tool.uv.sources]
   genai-tag-db-tools = { path = "local_packages/genai-tag-db-tools", editable = true }
   image-annotator-lib = { path = "local_packages/image-annotator-lib", editable = true }
   ```

2. 依存関係を同期する。
   ```bash
   uv sync --dev
   ```

3. 統合テストを実行する。
   ```bash
   uv run pytest -m integration
   ```

4. API に変更がある場合は統合コードを更新する。

### 非推奨 API の移行

**旧 API(非推奨)**:

```python
# DEPRECATED: Direct TagRepository usage
from genai_tag_db_tools.db.repository import TagRepository
repo = TagRepository()
tags = repo.search("blue eyes")  # ❌ Avoid
```

**新 API(推奨)**:

```python
# RECOMMENDED: Public API
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.models import TagSearchRequest

request = TagSearchRequest(tag_string="blue eyes")
results = search_tags(request)  # ✅ Use this
```

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — 開発概要
- [docs/services.md](services.md) — サービス層アーキテクチャ
- [docs/testing.md](testing.md) — テスト戦略
- [genai-tag-db-tools README](../local_packages/genai-tag-db-tools/README.md) — パッケージドキュメント
- [image-annotator-lib README](../local_packages/image-annotator-lib/README.md) — パッケージドキュメント
