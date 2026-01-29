# Plan: zany-twirling-cookie

**Created**: 2026-01-24 05:29:43
**Source**: plan_mode
**Original File**: zany-twirling-cookie.md
**Status**: planning

---

# Plan: zany-twirling-cookie (revised)

**Created**: 2026-01-24
**Updated**: 2026-01-24
**Source**: manual_sync
**Original File**: zany-twirling-cookie.md
**Status**: planning

---

# コードレビュー問題点修正計画（実出力ドリブンに見直し）

## 方針
- 先に **mypy / ruff の実出力** を取得し、症状→原因→最小修正の順で対応する。
- 型エラーの「件数」ではなく **具体的なエラーメッセージに基づく修正** に絞る。
- 返り値を `cast` で誤魔化すのは避け、**定義側で型保証**する。

---

## Phase 0: 診断（必須）

### 0.1 mypy / ruff 実行
```bash
uv run mypy src/lorairo/gui/widgets/thumbnail.py \
  src/lorairo/gui/widgets/batch_tag_add_widget.py \
  src/lorairo/gui/window/main_window.py \
  src/lorairo/gui/services/tab_reorganization_service.py \
  --pretty

uv run ruff check src/lorairo/gui/widgets/thumbnail.py \
  src/lorairo/gui/widgets/batch_tag_add_widget.py \
  src/lorairo/gui/window/main_window.py \
  src/lorairo/gui/services/tab_reorganization_service.py \
  tests/unit/gui/widgets/test_batch_tag_add_widget.py
```

### 0.2 記録
- エラーの **行番号・エラーコード・全文** を記録して、修正対象を確定する。

---

## Phase 1: thumbnail.py（型注釈は実エラーに合わせて）

### 1.1 目的
- mypy が `Any` / untyped-def を指摘している箇所のみ修正。

### 1.2 推奨方針
- `from __future__ import annotations` が未導入なら検討（型循環の回避）。
- Qt 型は `TYPE_CHECKING` で型専用 import（実行時負荷を減らす）。

### 1.3 例（mypy が untyped-def を指摘した場合のみ）
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QMouseEvent, QPainter, QResizeEvent
    from PySide6.QtWidgets import QStyleOptionGraphicsItem, QWidget

# 例: def paint(self, painter, option, widget):
# -> def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
```

---

## Phase 2: batch_tag_add_widget.py（cast 回避）

### 2.1 目的
- `TagCleaner.clean_format` の返り値型を **定義側で str に固定** する。

### 2.2 推奨修正（TagCleaner 定義側）
- 返り値が `Optional[str]` なら **None を正規化**して `str` を保証。

例：
```python
# TagCleaner.clean_format
# before: def clean_format(tag: str) -> str | None: ...
# after : def clean_format(tag: str) -> str:

cleaned = _internal_clean(tag)
return cleaned or ""  # または tag を返す方針でもOK
```

### 2.3 呼び出し側修正（必要なら）
- 定義側で `str` を保証できるなら `cast` は不要。
- 定義側を変えられない場合は明示ガードにする：
```python
cleaned = TagCleaner.clean_format(tag)
if cleaned is None:
    return ""
return cleaned.strip().lower()
```

---

## Phase 3: main_window.py（例外メッセージ露出の方針整理）

### 3.1 目的
- 例外の詳細はログに残し、UI には一般メッセージのみ表示。
- ただし **デバッグ性を下げない工夫** を加える。

### 3.2 推奨修正例
```python
except Exception as e:
    logger.error("Failed to show error log dialog", exc_info=True)
    QMessageBox.critical(
        self,
        "エラー",
        "表示に失敗しました。詳細はログを確認してください。",
    )
```

※ 必要なら DEBUG 設定時のみ詳細を表示する分岐を検討。

---

## Phase 4: tab_reorganization_service.py（findChild 型）

### 4.1 問題
- `findChild(object, name)` は緩いが確実。
- `QWidget` 固定は、`QAction` / `QLayout` などを含むと破綻する。

### 4.2 推奨方針
- **名前→型のマップ**を用意して型を明示。
- 型が不明なら `QObject` で検索し、後段で型チェック。

例：
```python
REQUIRED_WIDGET_TYPES = {
    "someWidget": QWidget,
    "someAction": QAction,
}
for name, klass in REQUIRED_WIDGET_TYPES.items():
    if not main_window.findChild(klass, name):
        missing_widgets.append(name)
```

---

## Phase 5: tests（RUF059 を簡潔に）

### 5.1 目的
- `widget, _ = widget_with_state` を **fixture 化** して冗長さを削減。

### 5.2 推奨修正
```python
@pytest.fixture
def widget_only(widget_with_state):
    widget, _ = widget_with_state
    return widget
```

各テストで `widget_only` を使う。

---

## 検証手順（確定後）

### 1. mypy
```bash
uv run mypy src/lorairo/gui/widgets/thumbnail.py \
  src/lorairo/gui/widgets/batch_tag_add_widget.py \
  src/lorairo/gui/window/main_window.py \
  src/lorairo/gui/services/tab_reorganization_service.py \
  --pretty
```

### 2. ruff
```bash
uv run ruff check src/lorairo/gui/widgets/thumbnail.py \
  src/lorairo/gui/widgets/batch_tag_add_widget.py \
  src/lorairo/gui/window/main_window.py \
  src/lorairo/gui/services/tab_reorganization_service.py \
  tests/unit/gui/widgets/test_batch_tag_add_widget.py
```

### 3. ユニットテスト
```bash
uv run pytest tests/unit/gui/widgets/test_batch_tag_add_widget.py \
  tests/unit/gui/widgets/test_thumbnail.py \
  tests/unit/gui/services/test_tab_reorganization_service.py -v
```

### 4. 統合テスト
```bash
uv run pytest tests/integration/gui/test_batch_tag_add_integration.py -v
```

---

## リスク評価（見直し）

| リスク | 影響度 | 対策 |
|--------|--------|------|
| cast による型の握りつぶし | 中 | 定義側で str を保証して回避 |
| findChild 型固定の取りこぼし | 中 | 名前→型マップ / QObject で回避 |
| QMessageBox 例外詳細削除で調査が困難 | 低 | ログ出力＋必要なら DEBUG 表示 |

---

## 作業見積り（再計測）
- Phase 0: 10–20分（実出力収集）
- Phase 1–5: 出力に応じて 30–90分
