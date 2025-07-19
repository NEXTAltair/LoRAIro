#!/usr/bin/env python3
# scripts/component_test.py

"""
コンポーネント単体テスト用スクリプト
主要なWidgetとコンポーネントの基本動作を確認
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

def test_imports():
    """全ての主要なクラスのインポートテスト"""
    print("=== インポートテスト ===")
    
    try:
        # データベース関連
        from lorairo.database.db_core import DefaultSessionLocal
        from lorairo.database.db_manager import ImageDatabaseManager
        from lorairo.database.db_repository import ImageRepository
        print("✅ データベース関連のインポート成功")
    except Exception as e:
        print(f"❌ データベース関連のインポートエラー: {e}")
        return False

    try:
        # サービス関連
        from lorairo.services.configuration_service import ConfigurationService
        from lorairo.services.worker_service import WorkerService
        print("✅ サービス関連のインポート成功")
    except Exception as e:
        print(f"❌ サービス関連のインポートエラー: {e}")
        return False

    try:
        # 状態管理
        from lorairo.gui.state.dataset_state import DatasetStateManager
        from lorairo.gui.state.workflow_state import WorkflowStateManager
        print("✅ 状態管理のインポート成功")
    except Exception as e:
        print(f"❌ 状態管理のインポートエラー: {e}")
        return False

    try:
        # GUI Widgetたち
        from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
        from lorairo.gui.widgets.preview_detail_panel import PreviewDetailPanel
        from lorairo.gui.widgets.thumbnail_enhanced import ThumbnailSelectorWidget
        from lorairo.gui.widgets.workflow_navigator import WorkflowNavigator
        print("✅ GUI Widgetのインポート成功")
    except Exception as e:
        print(f"❌ GUI Widgetのインポートエラー: {e}")
        return False

    try:
        # ワーカー関連
        from lorairo.gui.workers.base import SimpleWorkerBase
        from lorairo.gui.workers.search import SearchWorker
        print("✅ ワーカー関連のインポート成功")
    except Exception as e:
        print(f"❌ ワーカー関連のインポートエラー: {e}")
        return False

    try:
        # UI Designer関連
        from lorairo.gui.designer.MainWorkspaceWindow_ui import Ui_MainWorkspaceWindow
        print("✅ UI Designer関連のインポート成功")
    except Exception as e:
        print(f"❌ UI Designer関連のインポートエラー: {e}")
        return False

    try:
        # メインウィンドウ
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow
        print("✅ メインウィンドウのインポート成功")
    except Exception as e:
        print(f"❌ メインウィンドウのインポートエラー: {e}")
        return False

    return True

def test_basic_initialization():
    """基本的な初期化テスト（GUIなし）"""
    print("\n=== 基本初期化テスト ===")
    
    try:
        from lorairo.services.configuration_service import ConfigurationService
        config_service = ConfigurationService()
        print("✅ ConfigurationService 初期化成功")
    except Exception as e:
        print(f"❌ ConfigurationService 初期化エラー: {e}")
        return False

    try:
        from lorairo.storage.file_system import FileSystemManager
        fsm = FileSystemManager()
        print("✅ FileSystemManager 初期化成功")
    except Exception as e:
        print(f"❌ FileSystemManager 初期化エラー: {e}")
        return False

    try:
        from lorairo.database.db_core import DefaultSessionLocal
        from lorairo.database.db_repository import ImageRepository
        from lorairo.database.db_manager import ImageDatabaseManager
        
        image_repo = ImageRepository(session_factory=DefaultSessionLocal)
        db_manager = ImageDatabaseManager(image_repo, config_service, fsm)
        print("✅ ImageDatabaseManager 初期化成功")
    except Exception as e:
        print(f"❌ ImageDatabaseManager 初期化エラー: {e}")
        return False

    return True

def test_workers():
    """ワーカー関連のテスト"""
    print("\n=== ワーカーテスト ===")
    
    try:
        from lorairo.gui.workers.base import SimpleWorkerBase, WorkerProgress
        
        # テスト用の簡単なワーカー
        class TestWorker(SimpleWorkerBase):
            def execute(self):
                self.report_progress(50, "テスト中...")
                return "テスト完了"
        
        worker = TestWorker()
        assert worker.is_canceled() == False
        print("✅ SimpleWorkerBase 基本動作成功")
    except Exception as e:
        print(f"❌ SimpleWorkerBase テストエラー: {e}")
        return False

    try:
        from lorairo.gui.workers.progress_manager import ProgressManager
        # ProgressManagerはQWidgetが必要なのでここではスキップ
        print("✅ ProgressManager インポート成功")
    except Exception as e:
        print(f"❌ ProgressManager テストエラー: {e}")
        return False

    return True

def main():
    """メイン実行関数"""
    print("=" * 60)
    print("LoRAIro コンポーネント単体テスト")
    print("=" * 60)
    
    all_passed = True
    
    # インポートテスト
    if not test_imports():
        all_passed = False
    
    # 基本初期化テスト
    if not test_basic_initialization():
        all_passed = False
        
    # ワーカーテスト
    if not test_workers():
        all_passed = False
    
    # 結果出力
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 全てのテストが成功しました！")
        print("📋 主要コンポーネントは正常に実装されています")
        return 0
    else:
        print("❌ 一部のテストが失敗しました")
        print("🔧 失敗したコンポーネントの修正が必要です")
        return 1

if __name__ == "__main__":
    sys.exit(main())