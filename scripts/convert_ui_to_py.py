#!/usr/bin/env uv run python
"""
Phase 2変換済みUIファイルのPySide6-UIC変換スクリプト

Phase 2でレスポンシブ変換されたUIファイルを
PySide6-UCIコマンドでPythonコードに変換する
"""
import subprocess
import sys
from pathlib import Path
from loguru import logger


def main():
    """Phase 2変換済みUIファイルのPySide6-UIC変換実行"""
    
    logger.info("=== Phase 2変換済みUIファイル PySide6-UIC変換開始 ===")
    
    # Phase 2で変換済みのUIファイル
    phase2_ui_files = [
        "AnnotationDataDisplayWidget.ui", 
        "AnnotationResultsWidget.ui",
        "AnnotationStatusFilterWidget.ui",
        "ConfigurationWindow.ui",
        "DatasetExportWidget.ui",
        "DatasetOverviewWidget.ui",
        "DirectoryPickerWidget.ui",
        "FilePickerWidget.ui",
        "ImageEditWidget.ui",
        "ModelResultTab.ui",
        "ModelSelectionTableWidget.ui",
        "ModelSelectionWidget.ui",
        "PickerWidget.ui",
        "ProgressWidget.ui",
        "SelectedImageDetailsWidget.ui"
    ]
    
    # パス設定
    ui_dir = Path("src/lorairo/gui/designer")
    py_dir = Path("src/lorairo/gui/ui")  # 生成先ディレクトリ
    
    # 出力ディレクトリ作成
    py_dir.mkdir(parents=True, exist_ok=True)
    
    # __init__.pyファイル作成
    init_file = py_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Generated UI modules"""\n')
        
    success_count = 0
    failed_files = []
    
    for ui_file in phase2_ui_files:
        ui_path = ui_dir / ui_file
        py_filename = ui_file.replace('.ui', '.py').replace('Widget', '_ui').replace('Window', '_ui').replace('Tab', '_ui')
        py_path = py_dir / py_filename
        
        logger.info(f"Converting: {ui_file} -> {py_filename}")
        
        if not ui_path.exists():
            logger.error(f"UI file not found: {ui_path}")
            failed_files.append(ui_file)
            continue
            
        try:
            # PySide6-UIC実行
            result = subprocess.run([
                "uv", "run", "pyside6-uic",
                "--generator", "python",
                "--from-imports",  # 相対インポート使用
                "-o", str(py_path),
                str(ui_path)
            ], capture_output=True, text=True, check=True)
            
            if py_path.exists():
                logger.info(f"✅ Successfully converted: {py_filename}")
                success_count += 1
            else:
                logger.error(f"❌ Output file not created: {py_filename}")
                failed_files.append(ui_file)
                
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ PySide6-UIC error for {ui_file}: {e}")
            logger.error(f"STDERR: {e.stderr}")
            failed_files.append(ui_file)
        except Exception as e:
            logger.error(f"❌ Unexpected error for {ui_file}: {e}")
            failed_files.append(ui_file)
    
    # 結果サマリー
    total_files = len(phase2_ui_files)
    failed_count = len(failed_files)
    
    print(f"\n{'='*60}")
    print(f"📊 PYSIDE6-UIC CONVERSION SUMMARY")
    print(f"{'='*60}")
    print(f"📁 Total Files: {total_files}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    
    if failed_files:
        print(f"\n❌ Failed Files:")
        for file in failed_files:
            print(f"   - {file}")
    
    success_rate = success_count / total_files
    if success_rate >= 0.9:
        logger.info("✅ PySide6-UIC conversion completed successfully!")
        print(f"✅ Success Rate: {success_rate:.1%}")
        return 0
    else:
        logger.warning(f"⚠️ PySide6-UIC conversion completed with issues (success rate: {success_rate:.1%})")
        print(f"⚠️ Success Rate: {success_rate:.1%}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)