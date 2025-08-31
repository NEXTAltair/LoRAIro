"""
UIレスポンシブレイアウト自動変換サービス

Qt Designer .uiファイルを自動的にレスポンシブレイアウトに変換する
Phase 1で確立されたパターンを基に16ファイルの一括変換を提供
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from .configuration_service import ConfigurationService


@dataclass
class ConversionResult:
    """変換結果を表すデータクラス"""
    file_path: Path
    success: bool
    changes_made: int
    backup_path: Optional[Path] = None
    error_message: Optional[str] = None


@dataclass 
class ResponsivePattern:
    """レスポンシブパターン定義"""
    widget_types: List[str]
    target_properties: List[str]
    conversion_rules: Dict[str, str]
    validation_criteria: Dict[str, str]


class UIResponsiveConversionService:
    """UIファイルレスポンシブ変換サービス
    
    Qt Designer .uiファイルのレスポンシブレイアウト自動変換を提供
    - XMLパース・操作
    - パターンマッチング変換
    - バックアップ・復元機能
    - バリデーション統合
    """
    
    def __init__(self, config_service: ConfigurationService):
        """サービス初期化
        
        Args:
            config_service: 設定管理サービス
        """
        self._config_service = config_service
        self._ui_files_base_path = Path("src/lorairo/gui/designer")
        self._backup_directory = Path("backups/ui_conversion")
        self._patterns = self._initialize_responsive_patterns()
        
    def _initialize_responsive_patterns(self) -> Dict[str, ResponsivePattern]:
        """レスポンシブ変換パターン初期化
        
        Phase 1で確立されたパターンを詳細分析し、高精度変換ルールを定義
        """
        return {
            # コンテンツ表示エリア - 最大拡張
            "content_areas": ResponsivePattern(
                widget_types=["QScrollArea", "QTextEdit", "QGraphicsView", "QTreeView", "QListWidget"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Expanding",
                    "vsizetype": "Expanding"
                },
                validation_criteria={
                    "required_hsizetype": "Expanding",
                    "required_vsizetype": "Expanding"
                }
            ),
            
            # ダイアログボタン群 - 水平拡張、垂直固定
            "dialog_buttons": ResponsivePattern(
                widget_types=["QPushButton", "QDialogButtonBox"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Expanding",
                    "vsizetype": "Fixed"
                },
                validation_criteria={
                    "required_hsizetype": "Expanding",
                    "required_vsizetype": "Fixed"
                }
            ),
            
            # 入力フィールド - 水平拡張、垂直優先
            "input_fields": ResponsivePattern(
                widget_types=["QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Expanding",
                    "vsizetype": "Preferred"
                },
                validation_criteria={
                    "required_hsizetype": "Expanding",
                    "required_vsizetype": "Preferred"
                }
            ),
            
            # 表示専用ラベル - 水平優先、垂直固定
            "display_labels": ResponsivePattern(
                widget_types=["QLabel"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Preferred",
                    "vsizetype": "Fixed"
                },
                validation_criteria={
                    "required_hsizetype": "Preferred",
                    "required_vsizetype": "Fixed"
                }
            ),
            
            # コンテナフレーム - コンテキスト依存
            "container_frames": ResponsivePattern(
                widget_types=["QFrame", "QGroupBox", "QWidget"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Expanding",
                    "vsizetype": "Fixed"
                },
                validation_criteria={
                    "required_hsizetype": "Expanding",
                    "min_vsizetype": "Fixed"
                }
            ),
            
            # 水平レイアウト - マージン最小化
            "horizontal_layouts": ResponsivePattern(
                widget_types=["QHBoxLayout"],
                target_properties=["leftMargin", "topMargin", "rightMargin", "bottomMargin", "spacing"],
                conversion_rules={
                    "leftMargin": "0",
                    "topMargin": "0", 
                    "rightMargin": "0",
                    "bottomMargin": "0",
                    "spacing": "6"
                },
                validation_criteria={
                    "max_margin": "5",
                    "max_spacing": "15"
                }
            ),
            
            # 垂直レイアウト - 構造的スペーシング
            "vertical_layouts": ResponsivePattern(
                widget_types=["QVBoxLayout"],
                target_properties=["leftMargin", "topMargin", "rightMargin", "bottomMargin", "spacing"],
                conversion_rules={
                    "leftMargin": "5",
                    "topMargin": "5", 
                    "rightMargin": "5",
                    "bottomMargin": "5",
                    "spacing": "10"
                },
                validation_criteria={
                    "max_margin": "15",
                    "max_spacing": "20"
                }
            ),
            
            # プログレスバー - 全幅拡張
            "progress_indicators": ResponsivePattern(
                widget_types=["QProgressBar"],
                target_properties=["sizePolicy"],
                conversion_rules={
                    "hsizetype": "Expanding",
                    "vsizetype": "Fixed"
                },
                validation_criteria={
                    "required_hsizetype": "Expanding",
                    "required_vsizetype": "Fixed"
                }
            )
        }
        
    def convert_ui_files(self, target_files: Optional[List[str]] = None) -> List[ConversionResult]:
        """UIファイル群のレスポンシブ変換実行
        
        Args:
            target_files: 変換対象ファイル名リスト（Noneで全16ファイル）
            
        Returns:
            変換結果リスト
        """
        if target_files is None:
            target_files = self._get_all_ui_files()
            
        results = []
        
        for file_name in target_files:
            file_path = self._ui_files_base_path / file_name
            
            if not file_path.exists():
                results.append(ConversionResult(
                    file_path=file_path,
                    success=False,
                    changes_made=0,
                    error_message=f"File not found: {file_path}"
                ))
                continue
                
            try:
                result = self._convert_single_ui_file(file_path)
                results.append(result)
                logger.info(f"UI conversion completed: {file_name}, changes: {result.changes_made}")
                
            except Exception as e:
                logger.error(f"UI conversion failed: {file_name}, error: {e}")
                results.append(ConversionResult(
                    file_path=file_path,
                    success=False,
                    changes_made=0,
                    error_message=str(e)
                ))
                
        return results
        
    def _get_all_ui_files(self) -> List[str]:
        """変換対象の全UIファイルリスト取得"""
        # 実際にディレクトリに存在するUIファイルを動的に取得
        ui_files = []
        
        if self._ui_files_base_path.exists():
            ui_files = [f.name for f in self._ui_files_base_path.glob("*.ui")]
            ui_files.sort()  # アルファベット順にソート
            
        # ファイルが見つからない場合のフォールバック（手動リスト）
        if not ui_files:
            ui_files = [
                "AnnotationControlWidget.ui",
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
            
        return ui_files
        
    def _convert_single_ui_file(self, file_path: Path) -> ConversionResult:
        """単一UIファイルのレスポンシブ変換
        
        Args:
            file_path: 変換対象ファイルパス
            
        Returns:
            変換結果
        """
        # バックアップ作成
        backup_path = self._create_backup(file_path)
        
        # XML読み込み・解析
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"XML parse error in {file_path}: {e}")
            
        # XML構造検証
        if not self._validate_xml_structure(root):
            raise ValueError(f"Invalid XML structure in {file_path}")
            
        # 変換実行
        changes_made = 0
        for pattern_name, pattern in self._patterns.items():
            pattern_changes = self._apply_pattern_conversion(root, pattern)
            changes_made += pattern_changes
            logger.debug(f"Pattern {pattern_name}: {pattern_changes} changes applied")
            
        # 変更がある場合のみファイル更新
        if changes_made > 0:
            self._preserve_xml_formatting(tree, file_path)
            logger.info(f"UI file updated: {file_path}, total changes: {changes_made}")
            
        return ConversionResult(
            file_path=file_path,
            success=True,
            changes_made=changes_made,
            backup_path=backup_path
        )
        
    def _create_backup(self, file_path: Path) -> Path:
        """ファイルバックアップ作成
        
        Args:
            file_path: バックアップ対象ファイル
            
        Returns:
            バックアップファイルパス
        """
        self._backup_directory.mkdir(parents=True, exist_ok=True)
        
        # タイムスタンプ付きバックアップ名生成
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_backup_{timestamp}{file_path.suffix}"
        backup_path = self._backup_directory / backup_name
        
        import shutil
        shutil.copy2(file_path, backup_path)
        
        # バックアップメタデータ保存
        self._save_backup_metadata(backup_path, file_path)
        
        # 古いバックアップの自動削除
        self._cleanup_old_backups(file_path.stem)
        
        logger.debug(f"Backup created: {backup_path}")
        return backup_path
        
    def _save_backup_metadata(self, backup_path: Path, original_path: Path):
        """バックアップメタデータ保存
        
        Args:
            backup_path: バックアップファイルパス
            original_path: 元ファイルパス
        """
        import json
        from datetime import datetime
        
        metadata = {
            "original_file": str(original_path),
            "backup_created": datetime.now().isoformat(),
            "file_size": original_path.stat().st_size,
            "file_mtime": datetime.fromtimestamp(original_path.stat().st_mtime).isoformat()
        }
        
        metadata_path = backup_path.with_suffix(backup_path.suffix + ".meta")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
    def _cleanup_old_backups(self, file_stem: str, max_backups: int = 5):
        """古いバックアップファイルの削除
        
        Args:
            file_stem: ファイルベース名
            max_backups: 保持する最大バックアップ数
        """
        backup_pattern = f"{file_stem}_backup_*.ui"
        backup_files = list(self._backup_directory.glob(backup_pattern))
        
        if len(backup_files) > max_backups:
            # 作成時刻でソートし、古いものから削除
            backup_files.sort(key=lambda p: p.stat().st_ctime)
            
            for old_backup in backup_files[:-max_backups]:
                old_backup.unlink(missing_ok=True)
                # メタデータファイルも削除
                meta_file = old_backup.with_suffix(old_backup.suffix + ".meta")
                meta_file.unlink(missing_ok=True)
                logger.debug(f"Old backup removed: {old_backup}")
                
    def create_full_backup_snapshot(self) -> Path:
        """全UIファイルの完全バックアップスナップショット作成
        
        Returns:
            スナップショットディレクトリパス
        """
        from datetime import datetime
        import shutil
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self._backup_directory / f"full_snapshot_{timestamp}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        ui_files = list(self._ui_files_base_path.glob("*.ui"))
        
        for ui_file in ui_files:
            backup_file = snapshot_dir / ui_file.name
            shutil.copy2(ui_file, backup_file)
            
        logger.info(f"Full backup snapshot created: {snapshot_dir}")
        return snapshot_dir
        
    def restore_from_snapshot(self, snapshot_dir: Path) -> bool:
        """スナップショットからの完全復元
        
        Args:
            snapshot_dir: スナップショットディレクトリ
            
        Returns:
            復元成功フラグ
        """
        if not snapshot_dir.exists():
            logger.error(f"Snapshot directory not found: {snapshot_dir}")
            return False
            
        import shutil
        
        try:
            ui_files = list(snapshot_dir.glob("*.ui"))
            
            for ui_file in ui_files:
                target_file = self._ui_files_base_path / ui_file.name
                shutil.copy2(ui_file, target_file)
                logger.debug(f"File restored from snapshot: {target_file}")
                
            logger.info(f"Full restoration completed from: {snapshot_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Snapshot restoration failed: {e}")
            return False
        
    def _apply_pattern_conversion(self, root: ET.Element, pattern: ResponsivePattern) -> int:
        """パターンベース変換適用
        
        Args:
            root: XML root element
            pattern: 変換パターン
            
        Returns:
            適用した変更数
        """
        changes = 0
        
        # ダイアログタイプ判定によるコンテキスト調整
        dialog_context = self._analyze_dialog_context(root)
        adjusted_pattern = self._adjust_pattern_for_context(pattern, dialog_context)
        
        # 対象ウィジェット検索と変換適用
        for widget_type in adjusted_pattern.widget_types:
            # ウィジェット要素検索
            widgets = self._find_widgets_by_criteria(root, widget_class=widget_type)
            
            for widget in widgets:
                # コンテキスト依存フィルタリング
                if self._should_apply_pattern_to_widget(widget, adjusted_pattern, dialog_context):
                    widget_changes = self._apply_widget_conversion(widget, adjusted_pattern)
                    changes += widget_changes
                    
            # レイアウト要素検索 (QHBoxLayout, QVBoxLayoutなど)
            if widget_type.endswith("Layout"):
                layouts = root.findall(f".//{widget_type.lower()}")
                for layout in layouts:
                    if self._should_apply_pattern_to_layout(layout, adjusted_pattern):
                        layout_changes = self._apply_layout_conversion(layout, adjusted_pattern)
                        changes += layout_changes
                
        return changes
        
    def _analyze_dialog_context(self, root: ET.Element) -> Dict[str, str]:
        """ダイアログコンテキスト分析
        
        Args:
            root: XML root element
            
        Returns:
            ダイアログコンテキスト情報
        """
        class_element = root.find("class")
        if class_element is None:
            return {"type": "unknown", "category": "widget"}
            
        class_name = class_element.text
        
        # ダイアログタイプ判定
        dialog_type = "dialog" if "Dialog" in class_name else "widget"
        
        # ダイアログカテゴリ分類
        category = "standard"
        if "Progress" in class_name:
            category = "progress"
        elif "Settings" in class_name:
            category = "settings"  
        elif "Results" in class_name:
            category = "results"
        elif "Selection" in class_name:
            category = "selection"
            
        return {
            "type": dialog_type,
            "category": category,
            "class_name": class_name
        }
        
    def _adjust_pattern_for_context(self, pattern: ResponsivePattern, 
                                   context: Dict[str, str]) -> ResponsivePattern:
        """コンテキスト依存パターン調整
        
        Args:
            pattern: 元の変換パターン
            context: ダイアログコンテキスト
            
        Returns:
            調整済みパターン
        """
        # プログレスダイアログは特別な扱い
        if context["category"] == "progress":
            # プログレスバーを優先拡張
            if "QProgressBar" in pattern.widget_types:
                adjusted_rules = pattern.conversion_rules.copy()
                adjusted_rules["vsizetype"] = "Fixed"  # 高さ固定強制
                
                return ResponsivePattern(
                    widget_types=pattern.widget_types,
                    target_properties=pattern.target_properties,
                    conversion_rules=adjusted_rules,
                    validation_criteria=pattern.validation_criteria
                )
                
        # 設定ダイアログは入力フィールドを重視
        elif context["category"] == "settings":
            if any(wt in ["QLineEdit", "QComboBox"] for wt in pattern.widget_types):
                adjusted_rules = pattern.conversion_rules.copy()
                adjusted_rules["hsizetype"] = "Expanding"  # 水平拡張強化
                
                return ResponsivePattern(
                    widget_types=pattern.widget_types,
                    target_properties=pattern.target_properties,
                    conversion_rules=adjusted_rules,
                    validation_criteria=pattern.validation_criteria
                )
                
        return pattern  # 変更なし
        
    def _should_apply_pattern_to_widget(self, widget: ET.Element, 
                                       pattern: ResponsivePattern,
                                       context: Dict[str, str]) -> bool:
        """ウィジェット適用判定
        
        Args:
            widget: 対象ウィジェット要素
            pattern: 変換パターン
            context: ダイアログコンテキスト
            
        Returns:
            適用可能フラグ
        """
        # 既に最適化されているウィジェットのスキップ判定
        current_hsizetype = self._get_widget_property_value(widget, "sizePolicy", "hsizetype")
        current_vsizetype = self._get_widget_property_value(widget, "sizePolicy", "vsizetype")
        
        target_hsizetype = pattern.conversion_rules.get("hsizetype")
        target_vsizetype = pattern.conversion_rules.get("vsizetype")
        
        # 既に正しい値に設定されている場合はスキップ
        if (current_hsizetype == target_hsizetype and 
            current_vsizetype == target_vsizetype):
            return False
            
        # 特定条件下での適用回避
        widget_name = widget.get("name", "")
        
        # スペーサーウィジェットは変更しない
        if "spacer" in widget_name.lower():
            return False
            
        # カスタムサイズが明示的に設定されているウィジェットは慎重に扱う
        if self._has_explicit_size_constraints(widget):
            return False
            
        return True
        
    def _should_apply_pattern_to_layout(self, layout: ET.Element, 
                                       pattern: ResponsivePattern) -> bool:
        """レイアウト適用判定
        
        Args:
            layout: 対象レイアウト要素  
            pattern: 変換パターン
            
        Returns:
            適用可能フラグ
        """
        # ネストレベルが深すぎる場合は適用しない
        nesting_level = self._calculate_layout_nesting_level(layout)
        if nesting_level > 4:
            return False
            
        # マージン値が既に適切に設定されている場合
        for margin_prop in ["leftMargin", "topMargin", "rightMargin", "bottomMargin"]:
            current_value = self._get_layout_property_value(layout, margin_prop)
            target_value = pattern.conversion_rules.get(margin_prop)
            
            if target_value and current_value == target_value:
                continue
            else:
                return True  # 少なくとも1つの値に変更が必要
                
        return False
        
    def _has_explicit_size_constraints(self, widget: ET.Element) -> bool:
        """明示的サイズ制約の存在確認
        
        Args:
            widget: 対象ウィジェット
            
        Returns:
            明示的制約存在フラグ
        """
        size_properties = ["minimumSize", "maximumSize", "baseSize", "fixedSize"]
        
        for size_prop in size_properties:
            if widget.find(f".//property[@name='{size_prop}']") is not None:
                return True
                
        return False
        
    def _calculate_layout_nesting_level(self, layout: ET.Element) -> int:
        """レイアウトネストレベル計算
        
        Args:
            layout: 対象レイアウト要素
            
        Returns:
            ネストレベル (0が最上位)
        """
        level = 0
        parent = layout.getparent()
        
        while parent is not None:
            if parent.tag.lower().endswith("layout"):
                level += 1
            parent = parent.getparent()
            
        return level
        
    def _get_layout_property_value(self, layout: ET.Element, property_name: str) -> Optional[str]:
        """レイアウトプロパティ値取得
        
        Args:
            layout: レイアウト要素
            property_name: プロパティ名
            
        Returns:
            プロパティ値
        """
        property_elem = layout.find(f".//property[@name='{property_name}']")
        if property_elem is None:
            return None
            
        number_elem = property_elem.find(".//number")
        return number_elem.text if number_elem is not None else None
        
    def _apply_widget_conversion(self, widget: ET.Element, pattern: ResponsivePattern) -> int:
        """ウィジェット要素への変換適用"""
        changes = 0
        
        # sizePolicyプロパティ変更
        if "sizePolicy" in pattern.target_properties:
            changes += self._update_size_policy(widget, pattern.conversion_rules)
            
        return changes
        
    def _apply_layout_conversion(self, layout: ET.Element, pattern: ResponsivePattern) -> int:
        """レイアウト要素への変換適用"""
        changes = 0
        
        # マージン設定変更
        margin_properties = ["leftMargin", "topMargin", "rightMargin", "bottomMargin"]
        for prop in margin_properties:
            if prop in pattern.target_properties:
                changes += self._update_layout_margin(layout, prop, pattern.conversion_rules[prop])
                
        return changes
        
    def _update_size_policy(self, widget: ET.Element, rules: Dict[str, str]) -> int:
        """sizePolicyプロパティ更新"""
        changes = 0
        size_policy = widget.find(".//property[@name='sizePolicy']/sizepolicy")
        
        if size_policy is not None:
            # 既存sizepolicy更新
            if "hsizetype" in rules:
                hsizetype = size_policy.find("hsizetype")
                if hsizetype is not None and hsizetype.text != rules["hsizetype"]:
                    hsizetype.text = rules["hsizetype"]
                    changes += 1
                    
            if "vsizetype" in rules:
                vsizetype = size_policy.find("vsizetype")
                if vsizetype is not None and vsizetype.text != rules["vsizetype"]:
                    vsizetype.text = rules["vsizetype"]
                    changes += 1
        else:
            # sizepolicy新規作成
            changes += self._create_size_policy_element(widget, rules)
            
        return changes
        
    def _validate_xml_structure(self, root: ET.Element) -> bool:
        """XML構造の基本検証
        
        Args:
            root: XML root element
            
        Returns:
            検証成功フラグ
        """
        # Qt UI形式の基本要素確認
        if root.tag != "ui":
            logger.error("Invalid XML structure: root element is not 'ui'")
            return False
            
        # version属性確認
        version = root.get("version")
        if version not in ["4.0"]:
            logger.warning(f"Unexpected UI version: {version}")
            
        # class要素存在確認
        class_element = root.find("class")
        if class_element is None:
            logger.error("Invalid XML structure: missing 'class' element")
            return False
            
        # widget要素存在確認
        widget_element = root.find("widget")
        if widget_element is None:
            logger.error("Invalid XML structure: missing main 'widget' element")
            return False
            
        return True
        
    def _find_widgets_by_criteria(self, root: ET.Element, 
                                 widget_class: str = None,
                                 widget_name: str = None,
                                 has_property: str = None) -> List[ET.Element]:
        """複合条件でのウィジェット検索
        
        Args:
            root: XML root element
            widget_class: ウィジェットクラス名 (例: "QPushButton")
            widget_name: ウィジェット名 (例: "pushButtonOK")
            has_property: 必須プロパティ名 (例: "sizePolicy")
            
        Returns:
            マッチするウィジェット要素リスト
        """
        xpath_parts = [".//widget"]
        
        if widget_class:
            xpath_parts[0] += f"[@class='{widget_class}']"
            
        if widget_name:
            if "@" in xpath_parts[0]:
                xpath_parts[0] += f"[@name='{widget_name}']"
            else:
                xpath_parts[0] += f"[@name='{widget_name}']"
                
        widgets = root.findall(xpath_parts[0])
        
        # プロパティフィルタリング
        if has_property:
            widgets = [w for w in widgets 
                      if w.find(f".//property[@name='{has_property}']") is not None]
                      
        return widgets
        
    def _get_widget_property_value(self, widget: ET.Element, 
                                  property_name: str,
                                  sub_element: str = None) -> Optional[str]:
        """ウィジェットプロパティ値取得
        
        Args:
            widget: ウィジェット要素
            property_name: プロパティ名
            sub_element: サブ要素名 (例: sizepolicyのhsizetype)
            
        Returns:
            プロパティ値 (見つからない場合はNone)
        """
        property_elem = widget.find(f".//property[@name='{property_name}']")
        if property_elem is None:
            return None
            
        if sub_element:
            sub_elem = property_elem.find(f".//{sub_element}")
            return sub_elem.text if sub_elem is not None else None
        else:
            # 数値プロパティ
            number_elem = property_elem.find(".//number")
            if number_elem is not None:
                return number_elem.text
                
            # 文字列プロパティ  
            string_elem = property_elem.find(".//string")
            if string_elem is not None:
                return string_elem.text
                
            # ブールプロパティ
            bool_elem = property_elem.find(".//bool")
            if bool_elem is not None:
                return bool_elem.text
                
        return None
        
    def _preserve_xml_formatting(self, tree: ET.ElementTree, file_path: Path):
        """XMLフォーマット保持でファイル保存
        
        Qt Designerの標準的なフォーマットを維持してXML出力
        
        Args:
            tree: ElementTree
            file_path: 保存先ファイルパス
        """
        # インデント追加
        self._indent_xml_element(tree.getroot())
        
        # UTF-8、XML宣言付きで保存
        tree.write(
            file_path, 
            encoding="utf-8", 
            xml_declaration=True,
            method="xml"
        )
        
        # 改行コード統一
        self._normalize_line_endings(file_path)
        
    def _indent_xml_element(self, elem: ET.Element, level: int = 0):
        """XML要素の階層インデント追加
        
        Args:
            elem: インデント対象要素
            level: 現在の階層レベル
        """
        indent_str = "\n" + " " * level
        
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent_str + " "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent_str
            for child in elem:
                self._indent_xml_element(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent_str
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent_str
                
    def _normalize_line_endings(self, file_path: Path):
        """改行コード統一 (LF)
        
        Args:
            file_path: 対象ファイルパス
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # CRLF → LF変換
        content = content.replace('\r\n', '\n')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
    def _create_size_policy_element(self, widget: ET.Element, rules: Dict[str, str]) -> int:
        """sizepolicy要素新規作成"""
        property_elem = ET.SubElement(widget, "property")
        property_elem.set("name", "sizePolicy")
        
        sizepolicy_elem = ET.SubElement(property_elem, "sizepolicy")
        sizepolicy_elem.set("hsizetype", rules.get("hsizetype", "Preferred"))
        sizepolicy_elem.set("vsizetype", rules.get("vsizetype", "Preferred"))
        
        # horstretch, verstretch要素追加
        ET.SubElement(sizepolicy_elem, "horstretch").text = "0"
        ET.SubElement(sizepolicy_elem, "verstretch").text = "0"
        
        return 1
        
    def _update_layout_margin(self, layout: ET.Element, margin_name: str, value: str) -> int:
        """レイアウトマージン更新"""
        property_elem = layout.find(f".//property[@name='{margin_name}']")
        
        if property_elem is not None:
            number_elem = property_elem.find("number")
            if number_elem is not None and number_elem.text != value:
                number_elem.text = value
                return 1
        else:
            # プロパティ新規作成
            property_elem = ET.SubElement(layout, "property")
            property_elem.set("name", margin_name)
            ET.SubElement(property_elem, "number").text = value
            return 1
            
        return 0
        
    def validate_conversion_results(self, results: List[ConversionResult]) -> Dict[str, any]:
        """変換結果の詳細検証とサマリー生成
        
        Args:
            results: 変換結果リスト
            
        Returns:
            詳細検証サマリー
        """
        summary = {
            "total_files": len(results),
            "successful_conversions": sum(1 for r in results if r.success),
            "failed_conversions": sum(1 for r in results if not r.success),
            "total_changes": sum(r.changes_made for r in results),
            "files_with_changes": sum(1 for r in results if r.changes_made > 0),
            "validation_details": {},
            "qt_compatibility": {},
            "responsive_compliance": {}
        }
        
        # 詳細検証実行
        for result in results:
            if result.success and result.file_path.exists():
                file_validation = self._validate_converted_file(result.file_path)
                summary["validation_details"][result.file_path.name] = file_validation
                
        # Qt互換性チェック
        compatibility_results = self._check_qt_compatibility(results)
        summary["qt_compatibility"] = compatibility_results
        
        # レスポンシブ準拠度チェック
        compliance_results = self._check_responsive_compliance(results)
        summary["responsive_compliance"] = compliance_results
        
        return summary
        
    def _validate_converted_file(self, file_path: Path) -> Dict[str, any]:
        """変換済みファイルの詳細検証
        
        Args:
            file_path: 検証対象ファイル
            
        Returns:
            検証結果詳細
        """
        validation_result = {
            "xml_valid": False,
            "structure_valid": False,
            "responsive_elements": 0,
            "size_policy_issues": [],
            "layout_issues": [],
            "overall_score": 0.0
        }
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            validation_result["xml_valid"] = True
            
            # XML構造検証
            validation_result["structure_valid"] = self._validate_xml_structure(root)
            
            # レスポンシブ要素カウント
            responsive_widgets = self._count_responsive_elements(root)
            validation_result["responsive_elements"] = responsive_widgets
            
            # sizePolicyの問題チェック
            size_policy_issues = self._check_size_policy_issues(root)
            validation_result["size_policy_issues"] = size_policy_issues
            
            # レイアウトの問題チェック
            layout_issues = self._check_layout_issues(root)
            validation_result["layout_issues"] = layout_issues
            
            # 総合スコア計算
            validation_result["overall_score"] = self._calculate_validation_score(validation_result)
            
        except Exception as e:
            logger.error(f"File validation failed: {file_path}, error: {e}")
            
        return validation_result
        
    def _count_responsive_elements(self, root: ET.Element) -> int:
        """レスポンシブ要素数カウント
        
        Args:
            root: XML root element
            
        Returns:
            レスポンシブ設定済み要素数
        """
        count = 0
        
        # sizePolicy="Expanding"のウィジェット
        widgets_with_size_policy = root.findall(".//widget//property[@name='sizePolicy']")
        
        for policy in widgets_with_size_policy:
            sizepolicy = policy.find("sizepolicy")
            if sizepolicy is not None:
                hsizetype = sizepolicy.get("hsizetype", "")
                vsizetype = sizepolicy.get("vsizetype", "")
                
                if hsizetype == "Expanding" or vsizetype == "Expanding":
                    count += 1
                    
        return count
        
    def _check_size_policy_issues(self, root: ET.Element) -> List[Dict[str, str]]:
        """sizePolicyの問題チェック
        
        Args:
            root: XML root element
            
        Returns:
            問題リスト
        """
        issues = []
        
        # 各ウィジェットタイプの推奨設定と比較
        expected_policies = {
            "QScrollArea": {"hsizetype": "Expanding", "vsizetype": "Expanding"},
            "QTextEdit": {"hsizetype": "Expanding", "vsizetype": "Expanding"},
            "QPushButton": {"hsizetype": "Expanding", "vsizetype": "Fixed"},
            "QLineEdit": {"hsizetype": "Expanding", "vsizetype": "Preferred"}
        }
        
        for widget_class, expected in expected_policies.items():
            widgets = root.findall(f".//widget[@class='{widget_class}']")
            
            for widget in widgets:
                widget_name = widget.get("name", "unnamed")
                current_policy = self._get_widget_size_policy(widget)
                
                for policy_type, expected_value in expected.items():
                    current_value = current_policy.get(policy_type)
                    
                    if current_value != expected_value:
                        issues.append({
                            "widget_name": widget_name,
                            "widget_class": widget_class,
                            "policy_type": policy_type,
                            "current_value": current_value,
                            "expected_value": expected_value,
                            "severity": "medium"
                        })
                        
        return issues
        
    def _check_layout_issues(self, root: ET.Element) -> List[Dict[str, str]]:
        """レイアウトの問題チェック
        
        Args:
            root: XML root element
            
        Returns:
            問題リスト
        """
        issues = []
        
        # 過大なマージン/スペーシングチェック
        layouts = root.findall(".//layout")
        
        for layout in layouts:
            layout_name = layout.get("name", "unnamed")
            
            # マージンチェック
            for margin_prop in ["leftMargin", "topMargin", "rightMargin", "bottomMargin"]:
                margin_value = self._get_layout_property_value(layout, margin_prop)
                
                if margin_value and int(margin_value) > 20:
                    issues.append({
                        "layout_name": layout_name,
                        "property": margin_prop,
                        "current_value": margin_value,
                        "issue": "excessive_margin",
                        "severity": "low"
                    })
                    
            # スペーシングチェック
            spacing_value = self._get_layout_property_value(layout, "spacing")
            if spacing_value and int(spacing_value) > 25:
                issues.append({
                    "layout_name": layout_name,
                    "property": "spacing",
                    "current_value": spacing_value,
                    "issue": "excessive_spacing",
                    "severity": "low"
                })
                
        return issues
        
    def _get_widget_size_policy(self, widget: ET.Element) -> Dict[str, Optional[str]]:
        """ウィジェットのsizePolicy取得
        
        Args:
            widget: ウィジェット要素
            
        Returns:
            sizePolicyの詳細
        """
        policy_info = {
            "hsizetype": None,
            "vsizetype": None,
            "horstretch": None,
            "verstretch": None
        }
        
        size_policy = widget.find(".//property[@name='sizePolicy']/sizepolicy")
        
        if size_policy is not None:
            for key in policy_info.keys():
                value_elem = size_policy.find(key)
                if value_elem is not None:
                    policy_info[key] = value_elem.text
                else:
                    # 属性として設定されている場合
                    policy_info[key] = size_policy.get(key)
                    
        return policy_info
        
    def _calculate_validation_score(self, validation_data: Dict[str, any]) -> float:
        """バリデーションスコア計算
        
        Args:
            validation_data: バリデーション結果データ
            
        Returns:
            0.0-1.0のスコア
        """
        score = 0.0
        
        # XML妥当性 (30%)
        if validation_data["xml_valid"]:
            score += 0.3
            
        # 構造妥当性 (30%)
        if validation_data["structure_valid"]:
            score += 0.3
            
        # レスポンシブ要素比率 (25%)
        responsive_ratio = min(validation_data["responsive_elements"] / 10, 1.0)  # 10要素で満点
        score += responsive_ratio * 0.25
        
        # 問題の少なさ (15%)
        issue_count = len(validation_data["size_policy_issues"]) + len(validation_data["layout_issues"])
        issue_penalty = min(issue_count / 20, 1.0)  # 20問題で満点マイナス
        score += (1.0 - issue_penalty) * 0.15
        
        return round(score, 2)
        
    def _check_qt_compatibility(self, results: List[ConversionResult]) -> Dict[str, any]:
        """Qt互換性チェック
        
        Args:
            results: 変換結果リスト
            
        Returns:
            互換性チェック結果
        """
        compatibility = {
            "qt_version_support": "6.5+",
            "compatible_files": 0,
            "incompatible_files": 0,
            "compatibility_issues": []
        }
        
        for result in results:
            if result.success and result.file_path.exists():
                try:
                    tree = ET.parse(result.file_path)
                    root = tree.getroot()
                    
                    # version属性チェック
                    version = root.get("version")
                    if version and version == "4.0":
                        compatibility["compatible_files"] += 1
                    else:
                        compatibility["incompatible_files"] += 1
                        compatibility["compatibility_issues"].append({
                            "file": result.file_path.name,
                            "issue": "unsupported_ui_version",
                            "version": version
                        })
                        
                except Exception as e:
                    compatibility["incompatible_files"] += 1
                    compatibility["compatibility_issues"].append({
                        "file": result.file_path.name,
                        "issue": "xml_parse_error",
                        "error": str(e)
                    })
                    
        return compatibility
        
    def _check_responsive_compliance(self, results: List[ConversionResult]) -> Dict[str, any]:
        """レスポンシブ準拠度チェック
        
        Args:
            results: 変換結果リスト
            
        Returns:
            準拠度チェック結果
        """
        compliance = {
            "fully_compliant": 0,
            "partially_compliant": 0,
            "non_compliant": 0,
            "average_score": 0.0,
            "compliance_details": []
        }
        
        total_score = 0.0
        
        for result in results:
            if result.success and result.file_path.exists():
                file_validation = self._validate_converted_file(result.file_path)
                score = file_validation["overall_score"]
                total_score += score
                
                if score >= 0.8:
                    compliance["fully_compliant"] += 1
                elif score >= 0.5:
                    compliance["partially_compliant"] += 1
                else:
                    compliance["non_compliant"] += 1
                    
                compliance["compliance_details"].append({
                    "file": result.file_path.name,
                    "score": score,
                    "responsive_elements": file_validation["responsive_elements"],
                    "issues_count": len(file_validation["size_policy_issues"]) + len(file_validation["layout_issues"])
                })
                
        if results:
            compliance["average_score"] = round(total_score / len(results), 2)
            
        return compliance
        
    def restore_from_backup(self, result: ConversionResult) -> bool:
        """バックアップからの復元
        
        Args:
            result: 復元対象の変換結果
            
        Returns:
            復元成功フラグ
        """
        if result.backup_path is None or not result.backup_path.exists():
            logger.error(f"Backup not found for restoration: {result.file_path}")
            return False
            
        try:
            import shutil
            shutil.copy2(result.backup_path, result.file_path)
            logger.info(f"File restored from backup: {result.file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Restoration failed: {result.file_path}, error: {e}")
            return False