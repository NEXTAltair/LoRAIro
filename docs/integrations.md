# 外部パッケージ統合

## 概要

LoRAIroは2つのローカルパッケージと統合し、タグ管理とAIアノテーション機能を提供します。

**Local Packages:**
- `local_packages/genai-tag-db-tools` - Tag database management
- `local_packages/image-annotator-lib` - Multi-provider AI annotation

両パッケージは `uv.sources` でeditable installされ、プロジェクトルートの `.venv` を共有します。

## genai-tag-db-tools統合

### 目的

画像タグの正規化、検索、登録を外部タグデータベース（User DB + Base DB）で管理。

### 統合ポイント

#### 主要エントリーポイント

**File**: `src/lorairo/database/db_repository.py`

```python
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
```

**Usage:**
- Tag search: `search_tags(TagSearchRequest(...))`
- Tag registration: `TagRegisterService.register_tag(TagRegisterRequest(...))`
- Tag reader: `MergedTagReader` for user+base DB queries

#### Service Layer

**File**: `src/lorairo/services/tag_management_service.py`

```python
from genai_tag_db_tools.db.repository import TagReader  # User DB only
from genai_tag_db_tools.models import TagTypeUpdate
```

**Responsibility:**
- User DB専用タグ管理（Base DBは対象外）
- Unknown typeタグの検索と一括更新
- Type name一覧取得

#### GUI層

**File**: `src/lorairo/gui/widgets/tag_management_widget.py`

**Features:**
- Unknown typeタグの一覧表示
- Type選択UI
- 一括type更新

### 公開API使用方法

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

**Returns:** `TagSearchResponse` with matched tags

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

**Pattern:** Search → Register → Retry on conflict

**Conflict Handling:**
- format_id collision: Auto-increment within format scope
- Duplicate tag: Return existing tag_id

### データベースアーキテクチャ

#### User DB（主）

**Location:** `HF_HOME/.cache/genai-tag-db-tools/user_db.sqlite` (default)

**Initialization:**
```python
from genai_tag_db_tools.db.core import init_user_db

init_user_db(user_db_dir="path/to/user_db")  # Auto-created if not exists
```

**Strategy:**
- **Auto-creation**: LoRAIro auto-initializes at startup
- **format_id**: 1000+ range (reserved for user DB)
- **type_name**: Defaults to "unknown" placeholder
- **Isolation**: User-registered tags only

#### Base DB（オプション）

**Location:** 3 DB files downloaded from HuggingFace

**Contents:**
- Curated tag taxonomy
- Pre-registered tags from multiple formats
- Read-only for LoRAIro

**Merged Reader:**
```python
from genai_tag_db_tools.db.repository import MergedTagReader

reader = MergedTagReader()  # Combines User DB + Base DB
tags = reader.search_tags("blue eyes")  # Searches both DBs
```

### format_id衝突回避

**Problem:** User DB and Base DB may have overlapping format_ids (1-999)

**Solution:** 1000+ reservation for User DB

**Implementation:**
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

**Benefits:**
- No collision between User DB (1000+) and Base DB (1-999)
- format_id auto-increment scoped per format
- Safe concurrent registration

### タグタイプ管理

#### タイプ選択戦略

**Default:** `type_name="unknown"`

**User Assignment:**
1. List unknown tags: `TagManagementService.get_unknown_tags()`
2. List available types: `TagManagementService.get_all_available_types()`
3. Batch update: `TagManagementService.update_tag_types(tag_ids, new_type)`

**Type Names (examples):**
- `character` - Character names
- `copyright` - Series/game titles
- `general` - General descriptive tags
- `meta` - Metadata tags
- `unknown` - Unclassified (placeholder)

#### 一括更新API

```python
from genai_tag_db_tools.models import TagTypeUpdate

updates = [
    TagTypeUpdate(tag_id=1, type_name="character"),
    TagTypeUpdate(tag_id=2, type_name="general")
]

service.update_tags_type_batch(updates, format_name="Lorairo")
```

**Atomicity:** All updates succeed or rollback

### 統合テスト

**Coverage:** 75%+ for tag integration code

**Test Patterns:**
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

## image-annotator-lib統合

### 目的

Multi-provider AI annotation for image captioning and tagging (OpenAI, Anthropic, Google, Local models).

### 統合ポイント

#### 主要アダプター

**File**: `src/lorairo/annotations/annotator_adapter.py`

```python
from image_annotator_lib import get_available_annotators, create_annotator
from image_annotator_lib.types import AnnotationResult, AnnotatorConfig
```

**Responsibility:**
- Provider selection and configuration
- Annotator instance creation
- Result type conversion

#### アノテーションロジック

**File**: `src/lorairo/annotations/annotation_logic.py`

```python
from image_annotator_lib import annotate
from image_annotator_lib.types import AnnotationRequest
```

**Responsibility:**
- Annotation request construction
- Batch processing coordination
- Error handling and retry logic

#### Service Layer

**File**: `src/lorairo/services/annotator_library_adapter.py`

**Responsibility:**
- Business logic wrapper for annotation
- Configuration service integration
- Result aggregation

#### Worker層

**File**: `src/lorairo/gui/workers/annotation_worker.py`

**Responsibility:**
- Qt-based asynchronous annotation execution
- Progress reporting via Signals
- Result delivery to GUI

### プロバイダー設定

#### 設定ファイル

**File**: `config/lorairo.toml`

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
from src.lorairo.services.annotator_library_adapter import AnnotatorLibraryAdapter

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

```python
from src.lorairo.services.batch_processor import BatchProcessor

processor = BatchProcessor(annotator_adapter)
results = processor.process_batch(
    image_paths=["img1.jpg", "img2.jpg", ...],
    max_concurrent=5
)
```

### データ型

#### PHashAnnotationResults

**Structure:**
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

**Usage:**
- Store in database with phash as key
- Detect duplicate images via phash matching
- Version annotations per model/provider

### エラーハンドリング

#### リトライ戦略

```python
from src.lorairo.services.annotator_library_adapter import AnnotatorLibraryAdapter

adapter = AnnotatorLibraryAdapter(config)
result = adapter.annotate_with_retry(
    image_path="image.jpg",
    max_retries=3,
    backoff_factor=2.0
)
```

**Retry Conditions:**
- Network timeout
- Rate limit (429)
- Transient API errors (5xx)

**Non-Retry:**
- Invalid API key (401)
- Unsupported image format
- Image too large

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

#### 外部APIのモック

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

**Real API calls** (marked with `@pytest.mark.integration`):
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

**genai-tag-db-tools:**
- Minimum: 0.3.0 (public API support)
- Recommended: Latest (improved performance)

**image-annotator-lib:**
- Minimum: 0.2.0 (multi-provider support)
- Recommended: Latest (new provider support)

### 更新プロセス

1. Update `pyproject.toml`:
   ```toml
   [tool.uv.sources]
   genai-tag-db-tools = { path = "local_packages/genai-tag-db-tools", editable = true }
   image-annotator-lib = { path = "local_packages/image-annotator-lib", editable = true }
   ```

2. Sync dependencies:
   ```bash
   uv sync --dev
   ```

3. Run integration tests:
   ```bash
   uv run pytest -m integration
   ```

4. Update integration code if API changed

### 非推奨処理

**Old API (deprecated):**
```python
# DEPRECATED: Direct TagRepository usage
from genai_tag_db_tools.db.repository import TagRepository
repo = TagRepository()
tags = repo.search("blue eyes")  # ❌ Avoid
```

**New API (current):**
```python
# RECOMMENDED: Public API
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.models import TagSearchRequest

request = TagSearchRequest(tag_string="blue eyes")
results = search_tags(request)  # ✅ Use this
```

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - Development overview
- [docs/services.md](services.md) - Service layer architecture
- [docs/testing.md](testing.md) - Testing strategies
- [genai-tag-db-tools README](../local_packages/genai-tag-db-tools/README.md) - Package documentation
- [image-annotator-lib README](../local_packages/image-annotator-lib/README.md) - Package documentation
