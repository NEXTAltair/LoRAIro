# Plan: クイックフィルターボタン

**Created**: 2026-02-05
**Source**: manual_sync
**Original File**: search-ux-03-quick-filters.md
**Status**: planning

---

## 概要
よく使うフィルター組み合わせをワンクリックで適用できるボタンを追加する。

## 目的
- 作業フロー（アノテーション作業、品質チェック等）に合わせた即座の絞り込み
- 設定の手間削減
- 定型作業の効率化

---

## 実装方針

### アプローチ: プリセットボタン + お気に入りフィルター連携

事前定義のクイックフィルターボタンと、既存のお気に入りフィルター機能を組み合わせる。

---

## プリセットフィルター定義

### デフォルトクイックフィルター
| ボタン名 | 条件 | 用途 |
|---------|------|------|
| 未アノテーション | `only_untagged=True, only_uncaptioned=True` | アノテーション作業対象 |
| 高解像度 | `resolution_filter="1024x1024以上"` | 高品質画像の確認 |
| 今週追加 | `date_filter_enabled=True, date_range=過去7日` | 最近の追加画像 |
| 重複なし | `exclude_duplicates=True` | ユニーク画像のみ |
| 未評価 | `rating_filter="UNRATED"` | レーティング未設定 |

---

## 変更対象ファイル

### 1. QuickFilterPresets（新規作成）
**ファイル**: `src/lorairo/services/quick_filter_presets.py`

**責務**:
- プリセットフィルターの定義
- 条件辞書の生成

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class QuickFilterPreset:
    name: str
    icon: str | None  # アイコン名（オプション）
    tooltip: str
    conditions: dict[str, Any]

class QuickFilterPresets:
    """クイックフィルターのプリセット定義"""

    @staticmethod
    def get_presets() -> list[QuickFilterPreset]:
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        return [
            QuickFilterPreset(
                name="未アノテーション",
                icon="tag-off",
                tooltip="タグ・キャプションが未設定の画像",
                conditions={
                    "only_untagged": True,
                    "only_uncaptioned": True,
                }
            ),
            QuickFilterPreset(
                name="高解像度",
                icon="high-quality",
                tooltip="1024x1024以上の高解像度画像",
                conditions={
                    "resolution_filter": "1024x1024",
                }
            ),
            QuickFilterPreset(
                name="今週追加",
                icon="calendar-week",
                tooltip="過去7日間に追加された画像",
                conditions={
                    "date_filter_enabled": True,
                    "date_range_start": week_ago,
                    "date_range_end": now,
                }
            ),
            QuickFilterPreset(
                name="重複なし",
                icon="copy-off",
                tooltip="重複を除外したユニーク画像",
                conditions={
                    "exclude_duplicates": True,
                }
            ),
            QuickFilterPreset(
                name="未評価",
                icon="star-off",
                tooltip="レーティングが未設定の画像",
                conditions={
                    "rating_filter": "UNRATED",
                }
            ),
        ]
```

### 2. FilterSearchPanel（UI統合）
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

**追加内容**:
```python
def setup_quick_filters_ui(self) -> None:
    """クイックフィルターUIを作成"""
    self.quick_filters_layout = QHBoxLayout()

    presets = QuickFilterPresets.get_presets()
    for preset in presets:
        button = QPushButton(preset.name)
        button.setToolTip(preset.tooltip)
        button.setCheckable(True)  # トグル可能
        button.clicked.connect(
            lambda checked, p=preset: self._on_quick_filter_clicked(p, checked)
        )
        self.quick_filters_layout.addWidget(button)
        self._quick_filter_buttons[preset.name] = button

    # 「クリア」ボタン
    clear_button = QPushButton("クリア")
    clear_button.clicked.connect(self._clear_quick_filters)
    self.quick_filters_layout.addWidget(clear_button)

def _on_quick_filter_clicked(self, preset: QuickFilterPreset, checked: bool) -> None:
    """クイックフィルターボタンクリック時の処理"""
    if checked:
        # フィルター条件を適用
        self._apply_quick_filter(preset.conditions)
    else:
        # フィルターをリセット
        self._clear_filter_for_preset(preset)

def _apply_quick_filter(self, conditions: dict[str, Any]) -> None:
    """クイックフィルター条件を適用"""
    self._update_ui_from_conditions(conditions)
    self._on_filter_changed()  # カウント更新トリガー
```

### 3. FilterSearchPanel.ui（UI要素追加）
**ファイル**: `src/lorairo/gui/designer/FilterSearchPanel.ui`

**追加内容**:
- クイックフィルターグループボックス
- 水平レイアウトでボタンを配置
- 配置: 検索グループの直下

```xml
<widget class="QGroupBox" name="quickFiltersGroup">
  <property name="title">
    <string>クイックフィルター</string>
  </property>
  <layout class="QHBoxLayout" name="quickFiltersLayout">
    <!-- ボタンは動的に追加 -->
  </layout>
</widget>
```

---

## トグル動作

### ボタン状態管理
- **チェック状態**: フィルター適用中（ボタンがハイライト）
- **非チェック状態**: フィルターなし
- **複数選択可能**: 複数のクイックフィルターを組み合わせ可能

### 状態同期
```python
def _sync_quick_filter_buttons(self) -> None:
    """UIの状態とクイックフィルターボタンを同期"""
    current = self.get_current_conditions()
    for name, button in self._quick_filter_buttons.items():
        preset = self._get_preset_by_name(name)
        is_active = self._conditions_match_preset(current, preset.conditions)
        button.setChecked(is_active)
```

---

## お気に入りフィルターとの連携

既存の`FavoriteFiltersService`を活用し、カスタムクイックフィルターを保存可能に:
```python
def _save_as_quick_filter(self, name: str) -> None:
    """現在の条件をカスタムクイックフィルターとして保存"""
    conditions = self.get_current_conditions()
    self.favorite_filters_service.save_filter(f"quick:{name}", conditions)
```

---

## テスト計画

### ユニットテスト
- `tests/unit/services/test_quick_filter_presets.py`
  - プリセット定義の正確性
  - 条件辞書の形式確認

### GUIテスト
- `tests/unit/gui/widgets/test_filter_search_panel_quick_filters.py`
  - ボタンクリックでフィルター適用
  - トグル動作確認
  - 複数選択の組み合わせ

---

## 検証方法

1. アプリ起動: `uv run lorairo`
2. クイックフィルターボタンが表示されることを確認
3. 「未アノテーション」クリックでフィルター適用確認
4. ボタンのトグル状態が正しく反映されることを確認
5. テスト実行: `uv run pytest tests/unit/services/test_quick_filter_presets.py -v`

---

## 工数見積もり
- QuickFilterPresets実装: 小
- FilterSearchPanel統合: 中
- UI要素追加: 小
- テスト作成: 小
- **合計**: 小〜中
