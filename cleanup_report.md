# LoRAIro クリーンアップレポート

## 削除対象ファイル（旧GUIコンポーネント）

### 🗑️ 削除推奨ファイル

#### 1. 旧メインウィンドウシステム
- `src/lorairo/gui/window/main_window.py` - 旧メインウィンドウ（新MainWorkspaceWindowで置き換え済み）

#### 2. 旧個別ページシステム  
- `src/lorairo/gui/window/edit.py` - 旧画像編集ページ（新PreviewDetailPanelに統合済み）
- `src/lorairo/gui/window/export.py` - 旧エクスポートページ（新ActionToolbarに統合済み）
- `src/lorairo/gui/window/overview.py` - 旧概要ページ（新MainWorkspaceWindowに統合済み）
- `src/lorairo/gui/window/tagger.py` - 旧タガーページ（新PreviewDetailPanelに統合済み）

#### 3. 旧進捗システム
- `src/lorairo/gui/window/progress.py` - 旧進捗ウィンドウ（新ワーカーシステムで置き換え済み）

#### 4. 設定ウィンドウ（未使用）
- `src/lorairo/gui/window/configuration_window.py` - 設定ウィンドウ（実装されていない）

### ✅ 保持すべきファイル

#### 現在使用中
- `src/lorairo/gui/window/main_workspace_window.py` - 新メインワークスペース
- `src/lorairo/gui/window/__init__.py` - パッケージ初期化

## 影響分析

### 📋 削除の影響

#### 1. MainWindow_ui.py のインポートエラー
削除すると以下のファイルでインポートエラーが発生：
```python
# src/lorairo/gui/designer/MainWindow_ui.py
from ..window.configuration_window import ConfigurationWindow  # ❌
from ..window.edit import ImageEditWidget                       # ❌  
from ..window.export import DatasetExportWidget               # ❌
from ..window.overview import DatasetOverviewWidget           # ❌
from ..window.tagger import ImageTaggerWidget                 # ❌
```

#### 2. annotation_service.py のインポートエラー
```python
# src/lorairo/services/annotation_service.py
from ..gui.window.progress import Controller, Worker  # ❌
```

### 🔧 修正が必要な箇所

1. **MainWindow_ui.py**: 不要なインポートを削除
2. **annotation_service.py**: 新ワーカーシステムに移行
3. **依存性チェック**: 他にも影響する箇所がないか確認

## 実行計画

### Phase 1: 安全な削除
1. 未使用ファイルの特定完了 ✅
2. 依存関係の分析完了 ✅  
3. 影響箇所の修正準備

### Phase 2: 段階的削除
1. annotation_service.py の修正
2. MainWindow_ui.py の修正  
3. 旧ウィンドウファイルの削除
4. 動作確認

### Phase 3: 最終クリーンアップ
1. 不要なインポート削除
2. 未使用変数削除
3. 最終動作確認

## 削除により得られる効果

- **コードベースの簡素化**: 約6ファイル（~1500行）の削除
- **保守性向上**: 新アーキテクチャのみに集中可能
- **混乱防止**: 旧システムと新システムの併存による混乱を排除