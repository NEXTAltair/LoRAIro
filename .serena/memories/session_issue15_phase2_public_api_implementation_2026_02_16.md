# Issue #15 Phase 2: Public API定義 実装完了記録

**Date**: 2026-02-16  
**Branch**: NEXTAltair/issue15  
**Status**: Phase 2.3 完了、Phase 2.4-2.5 準備中

---

## Phase 2.1: 基盤構築 ✅

### 作成ファイル
- **src/lorairo/api/exceptions.py** (240行)
  - LoRAIroException 基底例外
  - プロジェクト関連: ProjectError, ProjectNotFoundError, ProjectAlreadyExistsError, ProjectOperationError
  - 画像関連: ImageError, ImageNotFoundError, DuplicateImageError, ImageRegistrationError
  - アノテーション関連: AnnotationError, AnnotationFailedError, APIKeyNotConfiguredError
  - エクスポート関連: ExportError, ExportFailedError, InvalidFormatError
  - タグ関連: TagError, TagNotFoundError, TagRegistrationError
  - その他: DatabaseError, ValidationError, InvalidInputError, InvalidPathError

- **src/lorairo/api/types.py** (200行)
  - Pydantic BaseModel でバリデーション付きデータ型定義
  - ProjectCreateRequest, ProjectInfo
  - ImageMetadata, RegistrationResult, DuplicateInfo
  - AnnotationResult, ModelInfo
  - ExportResult, ExportCriteria
  - TagSearchResult, TagInfo
  - PaginationInfo, PagedResult
  - StatusResponse, ErrorResponse

- **src/lorairo/api/__init__.py** (80行)
  - 例外・型・API関数のパブリック API エクスポート

---

## Phase 2.2: Service 実装 ✅

### 作成ファイル

**src/lorairo/services/project_management_service.py** (280行)
- `create_project(name, description)` - プロジェクト作成
- `list_projects()` - プロジェクト一覧
- `get_project(name)` - プロジェクト取得
- `delete_project(name)` - プロジェクト削除
- `update_project(name, description)` - プロジェクト更新
- メタデータ JSON 管理、ディレクトリ構造作成

**src/lorairo/services/image_registration_service.py** (180行)
- `register_images(directory, skip_duplicates)` - 画像登録
- `detect_duplicate_images(directory)` - 重複検出
- pHash 計算、サポート形式: JPG/JPEG/PNG/GIF/BMP/WEBP

### 修正ファイル

**src/lorairo/services/service_container.py**
- Import 追加: ProjectManagementService, ImageRegistrationService
- `__init__()` に新規 Service 属性初期化
- `project_management_service` property 追加
- `image_registration_service` property 追加
- `get_service_summary()` に新規 Service を記載
- `reset_container()` に新規 Service をクリア

---

## Phase 2.3: API ラップ実装 ✅

### 作成ファイル

**src/lorairo/api/project.py** (85行)
- `create_project(request)` - ProjectCreateRequest をラップ
- `list_projects()`
- `get_project(name)`
- `delete_project(name)`
- `update_project(name, description)`

**src/lorairo/api/images.py** (60行)
- `register_images(directory, skip_duplicates)`
- `detect_duplicate_images(directory)`

**src/lorairo/api/annotations.py** (70行)
- `annotate_images(model_names, image_ids)`
- APIキー検証
- 簡略実装（実運用時補完予定）

**src/lorairo/api/export.py** (75行)
- `export_dataset(project_name, output_path, criteria)`
- TXT/JSON 形式対応

**src/lorairo/api/tags.py** (45行)
- `get_unknown_tags()`
- `get_available_types()`

---

## 型チェック・品質確認

### mypy 結果
✅ 初期エラー修正完了
- InvalidFormatError の重複インポート削除
- TagManagementService メソッド名を実装に合わせる
- DatasetExportService メソッド呼び出し修正
- ConfigurationService.get_setting() に修正
- Pydantic 型制約で自動バリデーション

### API エクスポート確認
✅ `__init__.py` に API 関数を登録
- 関数: create_project, list_projects, get_project, delete_project, update_project, register_images, detect_duplicate_images, annotate_images, export_dataset, get_unknown_tags, get_available_types
- 例外: 25個の例外クラス
- 型: 15個のデータ型

---

## 設計パターン

### 1. Facade パターン
- 既存 Service を API 関数でラップ
- ServiceContainer から自動取得（遅延初期化）
- CLI/GUI双方で使用可能

### 2. 例外階層
- LoRAIroException 基底クラス
- カテゴリ別に階層化（Project, Image, Annotation, Export, Tag, Database, Validation）
- 統一的なエラーハンドリング

### 3. Pydantic データ型
- 入力値バリデーション自動化
- 型安全性向上（mypy 完全サポート）
- HTTP API 対応可能（JSON 自動変換）

### 4. Service レイヤー
- Qt 依存なし（CLI 使用可能）
- ビジネスロジック保護（UI とロジック分離）

---

## 次ステップ

### Phase 2.4: CLI 統合
- `cli/commands/project.py` を API層経由に修正
- `cli/commands/images.py` を API層経由に修正
- 既存 CLI テスト 64個のモック対象を API→Service に変更

### Phase 2.5: テスト・検証
- API レイヤーのユニットテスト (tests/unit/api/)
- 統合テスト (tests/integration/api/)
- 75%+ カバレッジ目標

---

## 備考

### 簡略実装箇所
- `annotations.py`: AnnotatorLibraryAdapter との統合は簡略化
  - 実運用時に実装詳細補完予定
  - スタブとして 0件成功を返す

- `tags.py`: TagManagementService の API が限定的
  - get_unknown_tags() と get_available_types() のみ対応
  - 将来的に search_tags(), register_tag() をサポート予定

### アーキテクチャ適合性
✅ 既存パターン踏襲
- ServiceContainer シングルトン統合
- Qt-free コアロジック設計と整合
- CLI/GUI 双方対応
- 例外処理統一

---

## ファイル一覧

```
src/lorairo/api/
├── __init__.py                          (API エクスポート)
├── exceptions.py                        (例外定義)
├── types.py                             (データ型定義)
├── project.py                           (プロジェクト API)
├── images.py                            (画像 API)
├── annotations.py                       (アノテーション API)
├── export.py                            (エクスポート API)
└── tags.py                              (タグ API)

src/lorairo/services/
├── project_management_service.py        (プロジェクト Service)
├── image_registration_service.py        (画像登録 Service)
└── service_container.py                 (更新: 新規 Service 登録)
```

---

## 合計行数

- API 層: 515行（例外+型+関数）
- Service 層: 460行（新規）
- Service 登録: 30行（修正）
- **合計: 1,005行**

---

## テスト準備状況

### Unit テスト対象
- `test_project_management_service.py`: 5-10件
- `test_image_registration_service.py`: 3-5件
- `test_api_project.py`: 5-7件
- `test_api_images.py`: 3-4件
- `test_api_annotations.py`: 2-3件
- `test_api_export.py`: 2-3件
- `test_api_tags.py`: 2-3件

### 統合テスト対象
- CLI → API → Service → DB フロー
- エラーハンドリング統一確認
- 例外伝播確認

---

## 状態

Phase 2.1-2.3 完了、実装可能な状態。
Phase 2.4-2.5 で CLI 統合・テスト実施予定。
