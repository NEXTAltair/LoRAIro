#!/usr/bin/env uv run python
"""
Phase 2: Qt Designer UIファイル レスポンシブレイアウト自動変換スクリプト

Phase 1で確立されたパターンを基に、残り16UIファイルを自動変換
- UIResponsiveConversionServiceによる高精度パターン変換
- 完全バックアップ・復元機能
- 詳細バリデーション・準拠度チェック
"""
import sys
from pathlib import Path
import json
from datetime import datetime
from loguru import logger

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from lorairo.services.configuration_service import ConfigurationService  
from lorairo.services.ui_responsive_conversion_service import UIResponsiveConversionService


def main():
    """Phase 2 UIレスポンシブ変換メイン実行"""
    
    logger.info("=== Phase 2: Qt Designer UIファイル レスポンシブレイアウト自動変換開始 ===")
    
    # 設定サービス初期化
    config_service = ConfigurationService()
    
    # 変換サービス初期化
    conversion_service = UIResponsiveConversionService(config_service)
    
    try:
        # 1. 完全バックアップスナップショット作成
        logger.info("Phase 2-1: 完全バックアップスナップショット作成")
        snapshot_path = conversion_service.create_full_backup_snapshot()
        logger.info(f"Backup snapshot created: {snapshot_path}")
        
        # 2. 残り16UIファイルの自動変換実行
        logger.info("Phase 2-2: 残り16UIファイル自動変換実行")
        target_files = get_phase2_target_files()
        
        logger.info(f"Target files for Phase 2 conversion: {len(target_files)} files")
        for file_name in target_files:
            logger.info(f"  - {file_name}")
        
        # 変換実行
        conversion_results = conversion_service.convert_ui_files(target_files)
        
        # 3. 変換結果の詳細検証
        logger.info("Phase 2-3: 変換結果詳細検証実行")
        validation_summary = conversion_service.validate_conversion_results(conversion_results)
        
        # 4. 結果レポート生成・出力
        logger.info("Phase 2-4: 結果レポート生成")
        report = generate_phase2_report(conversion_results, validation_summary, snapshot_path)
        
        report_path = save_conversion_report(report)
        logger.info(f"Conversion report saved: {report_path}")
        
        # 5. 結果サマリー表示
        print_conversion_summary(validation_summary)
        
        # 6. 成功判定
        success_rate = validation_summary["successful_conversions"] / validation_summary["total_files"]
        if success_rate >= 0.8:  # 80%以上成功
            logger.info("✅ Phase 2 conversion completed successfully!")
            return 0
        else:
            logger.warning(f"⚠️ Phase 2 conversion completed with issues (success rate: {success_rate:.1%})")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Phase 2 conversion failed: {e}")
        
        # エラー時の復元オプション提示
        if 'snapshot_path' in locals():
            response = input(f"Restore from backup snapshot? (y/N): ")
            if response.lower() in ['y', 'yes']:
                restoration_success = conversion_service.restore_from_snapshot(snapshot_path)
                if restoration_success:
                    logger.info("✅ Successfully restored from backup snapshot")
                else:
                    logger.error("❌ Snapshot restoration failed")
                    
        return 1


def get_phase2_target_files() -> list[str]:
    """Phase 2変換対象ファイルリスト取得
    
    実際のUIファイル構成から Phase 1で変換済みの4ファイルを除外し、残り16ファイルを対象とする
    """
    # 実際の全UIファイルリスト (src/lorairo/gui/designer/ から確認)
    all_ui_files = [
        "AnnotationControlWidget.ui",
        "AnnotationDataDisplayWidget.ui",
        "AnnotationResultsWidget.ui", 
        "AnnotationStatusFilterWidget.ui",
        "ConfigurationWindow.ui",
        "DatasetExportWidget.ui",
        "DatasetOverviewWidget.ui",
        "DirectoryPickerWidget.ui",
        "FilePickerWidget.ui",
        "FilterSearchPanel.ui",  # Phase 1完了済み
        "ImageEditWidget.ui",
        "ImagePreviewWidget.ui",  # Phase 1完了済み
        "MainWindow.ui",  # Phase 1完了済み
        "ModelResultTab.ui",
        "ModelSelectionTableWidget.ui",
        "ModelSelectionWidget.ui",
        "PickerWidget.ui",
        "ProgressWidget.ui",
        "SelectedImageDetailsWidget.ui",
        "ThumbnailSelectorWidget.ui"  # Phase 1完了済み
    ]
    
    # Phase 1完了済みファイル
    phase1_completed = [
        "FilterSearchPanel.ui",
        "ImagePreviewWidget.ui", 
        "MainWindow.ui",
        "ThumbnailSelectorWidget.ui"
    ]
    
    # Phase 2対象ファイル = 全体 - Phase 1完了済み
    phase2_targets = [f for f in all_ui_files if f not in phase1_completed]
    
    return phase2_targets


def generate_phase2_report(conversion_results: list, validation_summary: dict, 
                          snapshot_path: Path) -> dict:
    """Phase 2変換レポート生成
    
    Args:
        conversion_results: 変換結果リスト
        validation_summary: 検証サマリー
        snapshot_path: バックアップスナップショットパス
        
    Returns:
        詳細レポートデータ
    """
    report = {
        "phase": "Phase 2: Qt Designer UIファイル レスポンシブレイアウト自動変換",
        "execution_time": datetime.now().isoformat(),
        "backup_snapshot": str(snapshot_path),
        "conversion_summary": {
            "total_files": len(conversion_results),
            "successful_conversions": sum(1 for r in conversion_results if r.success),
            "failed_conversions": sum(1 for r in conversion_results if not r.success),
            "total_changes_applied": sum(r.changes_made for r in conversion_results),
            "files_with_changes": sum(1 for r in conversion_results if r.changes_made > 0)
        },
        "file_details": [],
        "validation_summary": validation_summary,
        "responsive_patterns_applied": {
            "content_areas": 0,
            "dialog_buttons": 0,
            "input_fields": 0,
            "display_labels": 0,
            "container_frames": 0,
            "layout_optimizations": 0
        },
        "quality_metrics": {
            "average_responsive_score": validation_summary.get("responsive_compliance", {}).get("average_score", 0.0),
            "qt_compatibility_rate": _calculate_compatibility_rate(validation_summary),
            "overall_success_rate": validation_summary["successful_conversions"] / validation_summary["total_files"]
        }
    }
    
    # ファイル別詳細情報
    for result in conversion_results:
        file_detail = {
            "file_name": result.file_path.name,
            "conversion_success": result.success,
            "changes_made": result.changes_made,
            "backup_created": str(result.backup_path) if result.backup_path else None,
            "error_message": result.error_message
        }
        
        # バリデーション詳細追加
        if result.file_path.name in validation_summary.get("validation_details", {}):
            file_validation = validation_summary["validation_details"][result.file_path.name]
            file_detail.update({
                "responsive_elements": file_validation.get("responsive_elements", 0),
                "validation_score": file_validation.get("overall_score", 0.0),
                "size_policy_issues": len(file_validation.get("size_policy_issues", [])),
                "layout_issues": len(file_validation.get("layout_issues", []))
            })
            
        report["file_details"].append(file_detail)
        
    return report


def _calculate_compatibility_rate(validation_summary: dict) -> float:
    """Qt互換性率計算"""
    qt_compat = validation_summary.get("qt_compatibility", {})
    total_files = qt_compat.get("compatible_files", 0) + qt_compat.get("incompatible_files", 0)
    
    if total_files == 0:
        return 0.0
        
    return qt_compat.get("compatible_files", 0) / total_files


def save_conversion_report(report: dict) -> Path:
    """変換レポートをJSONファイルに保存
    
    Args:
        report: レポートデータ
        
    Returns:
        保存先ファイルパス
    """
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"phase2_ui_conversion_report_{timestamp}.json"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    return report_path


def print_conversion_summary(validation_summary: dict):
    """変換結果サマリーをコンソール出力
    
    Args:
        validation_summary: 検証サマリー
    """
    print("\n" + "="*80)
    print("📊 PHASE 2 UI RESPONSIVE CONVERSION SUMMARY")
    print("="*80)
    
    # 基本統計
    print(f"📁 Total Files: {validation_summary['total_files']}")
    print(f"✅ Successful: {validation_summary['successful_conversions']}")
    print(f"❌ Failed: {validation_summary['failed_conversions']}")
    print(f"🔧 Total Changes: {validation_summary['total_changes']}")
    print(f"📝 Files Modified: {validation_summary['files_with_changes']}")
    
    # 準拠度情報
    compliance = validation_summary.get("responsive_compliance", {})
    if compliance:
        print(f"\n🎯 RESPONSIVE COMPLIANCE:")
        print(f"   Fully Compliant (≥80%): {compliance.get('fully_compliant', 0)}")
        print(f"   Partially Compliant (≥50%): {compliance.get('partially_compliant', 0)}")
        print(f"   Non-Compliant (<50%): {compliance.get('non_compliant', 0)}")
        print(f"   Average Score: {compliance.get('average_score', 0.0):.2f}/1.00")
    
    # Qt互換性
    compatibility = validation_summary.get("qt_compatibility", {})
    if compatibility:
        print(f"\n⚡ QT COMPATIBILITY:")
        print(f"   Compatible Files: {compatibility.get('compatible_files', 0)}")
        print(f"   Incompatible Files: {compatibility.get('incompatible_files', 0)}")
        
        if compatibility.get('compatibility_issues'):
            print(f"   Issues Found: {len(compatibility['compatibility_issues'])}")
    
    print("="*80)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)