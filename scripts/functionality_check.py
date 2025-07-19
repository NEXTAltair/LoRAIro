#!/usr/bin/env python3
# scripts/functionality_check.py

"""
実装計画に対する機能実装状況チェック
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

def check_dataset_state_methods():
    """DatasetStateManagerの機能チェック"""
    print("=== DatasetStateManager 機能チェック ===")
    
    try:
        from lorairo.gui.state.dataset_state import DatasetStateManager
        
        # クラス定義から実装されているメソッドを確認
        required_methods = [
            'set_dataset_path',
            'set_dataset_images', 
            'apply_filter_results',
            'set_selected_images',
            'clear_selection',
            'set_thumbnail_size',
            'set_layout_mode',
            'has_images',
            'has_filtered_images',
            'clear_filter'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(DatasetStateManager, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        else:
            print("✅ DatasetStateManager 全必要メソッド実装済み")
            return True
            
    except Exception as e:
        print(f"❌ DatasetStateManager エラー: {e}")
        return False

def check_filter_search_panel_methods():
    """FilterSearchPanelの機能チェック"""
    print("\n=== FilterSearchPanel 機能チェック ===")
    
    try:
        from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
        
        required_methods = [
            'update_search_preview',
            'clear_search_preview',
            '_create_search_section',
            '_create_filter_section',
            '_create_date_section',
            '_create_options_section',
            '_create_action_section'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(FilterSearchPanel, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        else:
            print("✅ FilterSearchPanel 主要メソッド実装済み")
            return True
            
    except Exception as e:
        print(f"❌ FilterSearchPanel エラー: {e}")
        return False

def check_thumbnail_enhanced_methods():
    """ThumbnailSelectorWidgetの機能チェック"""
    print("\n=== ThumbnailSelectorWidget 機能チェック ===")
    
    try:
        from lorairo.gui.widgets.thumbnail_enhanced import ThumbnailSelectorWidget
        
        required_methods = [
            'load_images_from_metadata',
            'load_thumbnails_from_result',
            'clear_thumbnails',
            '_update_display_mode'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(ThumbnailSelectorWidget, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        else:
            print("✅ ThumbnailSelectorWidget 主要メソッド実装済み")
            return True
            
    except Exception as e:
        print(f"❌ ThumbnailSelectorWidget エラー: {e}")
        return False

def check_worker_service_methods():
    """WorkerServiceの機能チェック"""
    print("\n=== WorkerService 機能チェック ===")
    
    try:
        from lorairo.services.worker_service import WorkerService
        
        required_methods = [
            'start_batch_registration',
            'start_search',
            'start_thumbnail_loading',
            'start_annotation',
            'cancel_search',
            'cancel_thumbnail_loading',
            'get_active_worker_count',
            'cancel_all_workers',
            'wait_for_all_workers'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(WorkerService, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        else:
            print("✅ WorkerService 主要メソッド実装済み")
            return True
            
    except Exception as e:
        print(f"❌ WorkerService エラー: {e}")
        return False

def check_preview_detail_panel_methods():
    """PreviewDetailPanelの機能チェック"""
    print("\n=== PreviewDetailPanel 機能チェック ===")
    
    try:
        from lorairo.gui.widgets.preview_detail_panel import PreviewDetailPanel
        
        required_methods = [
            '_create_preview_section',
            '_create_metadata_section', 
            '_create_annotations_section',
            '_connect_dataset_state',
            '_update_preview_image',
            '_update_metadata_display'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(PreviewDetailPanel, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        else:
            print("✅ PreviewDetailPanel 主要メソッド実装済み")
            return True
            
    except Exception as e:
        print(f"❌ PreviewDetailPanel エラー: {e}")
        return False

def check_main_workspace_functionality():
    """MainWorkspaceWindowの主要機能チェック"""
    print("\n=== MainWorkspaceWindow 主要機能チェック ===")
    
    try:
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow
        
        # シグナルの存在確認
        required_signals = [
            'dataset_loaded',
            'database_registration_completed'
        ]
        
        for signal_name in required_signals:
            if not hasattr(MainWorkspaceWindow, signal_name):
                print(f"❌ 不足シグナル: {signal_name}")
                return False
        
        # 重要メソッドの存在確認
        required_methods = [
            'setup_custom_widgets',
            'setup_connections',
            'select_dataset',
            'load_dataset',
            'start_image_registration',
            'on_search_requested',
            'on_filter_cleared',
            'get_window_state_summary'
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(MainWorkspaceWindow, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"❌ 不足メソッド: {missing_methods}")
            return False
        
        print("✅ MainWorkspaceWindow 主要機能実装済み")
        return True
        
    except Exception as e:
        print(f"❌ MainWorkspaceWindow エラー: {e}")
        return False

def main():
    """メイン実行関数"""
    print("=" * 60)
    print("LoRAIro 機能実装状況チェック")
    print("=" * 60)
    
    all_passed = True
    
    # 各コンポーネントの機能チェック
    checks = [
        check_dataset_state_methods,
        check_filter_search_panel_methods,
        check_thumbnail_enhanced_methods,
        check_worker_service_methods,
        check_preview_detail_panel_methods,
        check_main_workspace_functionality
    ]
    
    for check_func in checks:
        if not check_func():
            all_passed = False
    
    # 結果出力
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 全ての主要機能が実装されています！")
        print("📋 実装計画に従った機能は正常に実装済み")
        return 0
    else:
        print("⚠️ 一部の機能が不足しています")
        print("🔧 不足している機能の実装が必要です")
        return 1

if __name__ == "__main__":
    sys.exit(main())