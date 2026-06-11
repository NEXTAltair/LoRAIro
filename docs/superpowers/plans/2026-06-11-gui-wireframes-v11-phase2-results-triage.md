# GUI Wireframes v11 — Phase 2 Results 読み取り専用トリアージ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wireframes v11 Frame 5「Results」を読み取り専用のアノテーション品質トリアージ画面として実装し、Phase 1 の `tabResults` スタブを置換する。

**Architecture:** Qt-free の `QualityIssueDetectionService`（純粋な分類ロジック）と Qt の `ResultsWidget`（表示）を分離し、MainWindow が両者を仲介する MVC 構成。検出は**構造的事実 5 種のみ**で閾値は持たない。データソースは共有ステージング集合（Phase 1 で全タブ共有済み）。

**Tech Stack:** PySide6 / pytest-qt / 既存 `domain/quality_tier.py` `domain/score_scaler.py` / `db_manager.get_image_annotations`

---

## 確定スコープ（ユーザー承認済 2026-06-11）

- **読み取り専用トリアージ**: サマリ band + issue カード + per-image 行の「表示」まで。accept/edit/reject アクション・bulk 承認・永続化は **Phase 2b** に分離
- **検出閾値は持たない**: 低信頼度タグ・短 caption は issue 化せず、行内にデータとして表示するのみ。issue 検出は構造的事実 5 種:
  1. `EMPTY_TAGS` — tagger 由来の採用タグが 0 件
  2. `NO_SCORE` — scorer 出力（score / score_label）が無い
  3. `UNKNOWN_TIER` — score_label が `map_score_label_to_tier` で None（mapping 未定義、ADR 0028）
  4. `RATING_DISAGREEMENT` — 複数モデルの `normalized_rating` が割れている
  5. `SCORER_DISAGREEMENT` — 複数 scorer の tier が割れている（`is_unanimous == false` 相当）
- **`Image.reviewed_at` migration は Phase 2b**（accept アクションと同時。本フェーズでは未使用カラムを足さない＝YAGNI）
- **データソース** = 共有ステージング集合の image_ids（`dataset_state_manager` / staging widget 経由、Export と同じ「有界・可視・名前付き集合」ADR 0055）

---

## 背景と既存資産

- 設計: `docs/design/wireframes-v11/wireframes-v11.html` の `data-screen-label="05 Results"`（Frame 5）
- `src/lorairo/domain/quality_tier.py`: `QualityTier(IntEnum)`, `map_score_label_to_tier(model, label) -> QualityTier | None`, `map_manual_score_to_tier`
- `src/lorairo/domain/score_scaler.py`: `calibrate_to_display`, `select_positive_score` 等（raw → 表示スコア）
- `db_manager.get_image_annotations(image_id, *, include_rejected=False)` → dict:
  - `tags`: `[{id, tag, tag_id, model_id, confidence_score, rejected_at, is_edited_manually, existing, ...}]`
  - `captions`: `[{id, caption, model_id, rejected_at, ...}]`
  - `scores`: `[{id, score, model_id, ...}]`
  - `score_labels`: `[{id, label, model_id, model, ...}]`（ADR 0028: model 名と組）
  - `ratings`: `[{id, raw_rating_value, normalized_rating, model_id, model, source, confidence_score, ...}]`
- Phase 1 スタブ: `MainWindow.ui` の `tabResults`（`labelResultsStub` を内包する `verticalLayout_results`）

---

## File Structure

| ファイル | 担当 Track | 内容 |
|---|---|---|
| `src/lorairo/services/quality_issue_detection_service.py` | Lead(契約)+A | 契約 dataclass + 検出ロジック実装 |
| `tests/unit/services/test_quality_issue_detection_service.py` | A | 検出ロジックの unit テスト |
| `src/lorairo/gui/widgets/results_widget.py` | Lead(契約)+B | ResultsWidget（表示、純コード QWidget） |
| `tests/unit/gui/widgets/test_results_widget.py` | B | widget 表示テスト（hand-built dataclass 入力） |
| `src/lorairo/gui/window/main_window.py` | Lead(C) | `_setup_results_tab` + Results タブ表示時の wiring |
| `tests/integration/test_main_window_tab_integration.py` | Lead(C) | Results 埋め込み統合テスト |

**ファイル集合は Track A / B / C で完全に disjoint** → 並列マージ無衝突。論理結合は下記「共有契約」で吸収。

---

## 共有契約（Lead が Task 1 で先行コミット。Track A/B はこれを import するだけ）

`src/lorairo/services/quality_issue_detection_service.py` の冒頭に定義:

```python
from dataclasses import dataclass, field
from enum import Enum

from lorairo.domain.quality_tier import QualityTier


class IssueType(Enum):
    """構造的品質問題の種別（閾値非依存）。"""

    EMPTY_TAGS = "empty_tags"
    NO_SCORE = "no_score"
    UNKNOWN_TIER = "unknown_tier"
    RATING_DISAGREEMENT = "rating_disagreement"
    SCORER_DISAGREEMENT = "scorer_disagreement"


@dataclass(frozen=True)
class TagView:
    """行表示用のタグ（採用分のみ）。"""

    tag: str
    confidence_score: float | None
    model_id: int | None


@dataclass(frozen=True)
class RatingView:
    """モデル別 rating。"""

    model: str
    normalized_rating: str | None
    confidence_score: float | None


@dataclass(frozen=True)
class ScorerView:
    """モデル別 scorer 判定。"""

    model: str
    label: str | None
    tier: QualityTier | None  # mapping 不能なら None


@dataclass(frozen=True)
class ImageTriageResult:
    """1 画像分のトリアージ結果。"""

    image_id: int
    uuid: str | None
    width: int | None
    height: int | None
    tags: list[TagView]
    caption: str | None
    caption_word_count: int
    canonical_rating: str | None          # 最も厳しい normalized_rating
    ratings: list[RatingView]
    canonical_tier: QualityTier | None    # scorer tier の median 相当
    scorers: list[ScorerView]
    issues: list[IssueType]               # 検出された構造的問題（空なら clean）

    @property
    def needs_review(self) -> bool:
        return len(self.issues) > 0


@dataclass(frozen=True)
class BatchTriageSummary:
    """バッチ全体のサマリ。"""

    batch_size: int
    needs_review_count: int
    clean_count: int
    issue_counts: dict[IssueType, int]    # issue 種別ごとの件数
    tier_distribution: dict[QualityTier, int]
    no_tier_count: int                    # tier 算出不能（no-score/unknown）の件数


class QualityIssueDetectionService:
    """ステージング集合のアノテーションを構造的品質問題に分類する（Qt-free）。"""

    def detect_image(self, image_id: int, image_meta: dict, annotations: dict) -> ImageTriageResult:
        """1 画像のアノテーションをトリアージする。

        Args:
            image_id: 画像 ID。
            image_meta: ``{"uuid": str|None, "width": int|None, "height": int|None}``。
            annotations: ``db_manager.get_image_annotations`` の戻り（tags/captions/scores/score_labels/ratings）。
        """
        raise NotImplementedError

    def summarize(self, results: list[ImageTriageResult]) -> BatchTriageSummary:
        """画像別結果をバッチサマリに集約する。"""
        raise NotImplementedError
```

`ResultsWidget` の公開 API（Track B 実装、Track C が呼ぶ）:

```python
class ResultsWidget(QWidget):
    """Frame 5 · Results 読み取り専用トリアージ表示。objectName = "resultsWidget"。"""

    review_requested = Signal(int)  # image_id（Annotate へ遷移要求。Phase 2b で接続）

    def __init__(self, parent: QWidget | None = None) -> None: ...

    def display(self, summary: BatchTriageSummary, results: list[ImageTriageResult]) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。"""

    def clear(self) -> None:
        """空状態（ステージング 0 件）を表示する。"""
```

---

### Task 1: 共有契約の先行コミット（Lead）

**Files:**
- Create: `src/lorairo/services/quality_issue_detection_service.py`（上記契約、メソッドは `NotImplementedError`）
- Create: `src/lorairo/gui/widgets/results_widget.py`（`display`/`clear` は `pass` のスタブ、契約 import）

- [ ] **Step 1: 契約ファイルを作成**（上記「共有契約」のコード全文）
- [ ] **Step 2: ResultsWidget スタブを作成**

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    ImageTriageResult,
)


class ResultsWidget(QWidget):
    review_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsWidget")
        self._root = QVBoxLayout(self)

    def display(self, summary: BatchTriageSummary, results: list[ImageTriageResult]) -> None:
        pass

    def clear(self) -> None:
        pass
```

- [ ] **Step 3: import が通ることを確認**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync python -c "from lorairo.gui.widgets.results_widget import ResultsWidget; from lorairo.services.quality_issue_detection_service import QualityIssueDetectionService, IssueType, ImageTriageResult, BatchTriageSummary; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: コミット**

```bash
git add src/lorairo/services/quality_issue_detection_service.py src/lorairo/gui/widgets/results_widget.py
git commit -m "feat(results): Phase 2 共有契約 (dataclass + service/widget skeleton) を追加"
```

---

### Task A: QualityIssueDetectionService の検出ロジック実装（Track A・並列）

**Files:**
- Modify: `src/lorairo/services/quality_issue_detection_service.py`（`detect_image` / `summarize` 実装）
- Create: `tests/unit/services/test_quality_issue_detection_service.py`

**検出ルール（閾値なし・構造的事実のみ）:**

- `EMPTY_TAGS`: 採用タグ（`rejected_at is None`）が 0 件。`annotations["tags"]` が空、または全て rejected。
- `NO_SCORE`: `annotations["scores"]` と `annotations["score_labels"]` が両方空。
- `UNKNOWN_TIER`: いずれかの `score_label` で `map_score_label_to_tier(sl["model"], sl["label"]) is None`。
- `RATING_DISAGREEMENT`: `annotations["ratings"]` のうち `normalized_rating` の distinct 値が 2 以上。
- `SCORER_DISAGREEMENT`: score_label を tier に map した結果（None 除く）の distinct 値が 2 以上。

**集約ルール:**

- `canonical_rating`: ratings の `normalized_rating` のうち最も厳しい値（順序 `PG < PG-13 < R < X < XXX`）。
- `canonical_tier`: scorer tier（None 除く）の中央値（偶数個は厳しい側＝小さい ordinal を採用、要 docstring 明記）。None しか無ければ None。
- `caption_word_count`: 採用 caption（最初の `rejected_at is None`）を空白 split した語数。caption 無しは 0。
- `tags`: 採用タグを `TagView` に（confidence 降順）。

- [ ] **Step 1: 失敗するテストを書く**（各 issue 種別 + clean + summarize。最低 8 ケース）

```python
import pytest

from lorairo.domain.quality_tier import QualityTier
from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    IssueType,
    QualityIssueDetectionService,
)

META = {"uuid": "abcd", "width": 1024, "height": 1024}


@pytest.fixture
def service() -> QualityIssueDetectionService:
    return QualityIssueDetectionService()


def _ann(*, tags=None, captions=None, scores=None, score_labels=None, ratings=None) -> dict:
    return {
        "tags": tags or [],
        "captions": captions or [],
        "scores": scores or [],
        "score_labels": score_labels or [],
        "ratings": ratings or [],
    }


def test_empty_tags_detected(service):
    result = service.detect_image(1, META, _ann(tags=[], score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}]))
    assert IssueType.EMPTY_TAGS in result.issues


def test_all_rejected_tags_count_as_empty(service):
    rejected = [{"tag": "x", "confidence_score": 0.9, "model_id": 1, "rejected_at": "2026-01-01"}]
    result = service.detect_image(1, META, _ann(tags=rejected))
    assert IssueType.EMPTY_TAGS in result.issues


def test_no_score_detected(service):
    result = service.detect_image(1, META, _ann(tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}]))
    assert IssueType.NO_SCORE in result.issues


def test_unknown_tier_detected(service):
    sl = [{"model": "waifu_aesthetic", "label": "tier_2"}]
    result = service.detect_image(1, META, _ann(tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}], score_labels=sl))
    assert IssueType.UNKNOWN_TIER in result.issues


def test_rating_disagreement_detected(service):
    ratings = [
        {"model": "wd-rater", "normalized_rating": "R", "confidence_score": 0.7},
        {"model": "gpt-4o", "normalized_rating": "PG", "confidence_score": 0.6},
    ]
    result = service.detect_image(1, META, _ann(tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}], score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}], ratings=ratings))
    assert IssueType.RATING_DISAGREEMENT in result.issues
    assert result.canonical_rating == "R"  # 厳しい方


def test_scorer_disagreement_detected(service):
    sl = [
        {"model": "aesthetic_shadow_v2", "label": "aesthetic"},      # BEST_QUALITY
        {"model": "aesthetic_shadow_v2", "label": "displeasing"},    # LOW_QUALITY
    ]
    result = service.detect_image(1, META, _ann(tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}], score_labels=sl))
    assert IssueType.SCORER_DISAGREEMENT in result.issues


def test_clean_image_has_no_issues(service):
    ann = _ann(
        tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
        captions=[{"caption": "a young woman walking a dog in the city", "rejected_at": None}],
        score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
        ratings=[{"model": "wd-rater", "normalized_rating": "PG", "confidence_score": 0.9}],
    )
    result = service.detect_image(1, META, ann)
    assert result.issues == []
    assert result.needs_review is False
    assert result.caption_word_count == 8
    assert result.canonical_tier == QualityTier.BEST_QUALITY


def test_summarize_counts(service):
    clean = service.detect_image(1, META, _ann(
        tags=[{"tag": "a", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
        score_labels=[{"model": "aesthetic_shadow_v2", "label": "aesthetic"}],
        ratings=[{"model": "wd-rater", "normalized_rating": "PG", "confidence_score": 0.9}],
    ))
    bad = service.detect_image(2, META, _ann())  # empty everything → EMPTY_TAGS + NO_SCORE
    summary = service.summarize([clean, bad])
    assert summary.batch_size == 2
    assert summary.needs_review_count == 1
    assert summary.clean_count == 1
    assert summary.issue_counts[IssueType.EMPTY_TAGS] == 1
    assert summary.issue_counts[IssueType.NO_SCORE] == 1
```

- [ ] **Step 2: テスト実行で失敗確認**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/services/test_quality_issue_detection_service.py -v --timeout=60
```

Expected: FAIL（`NotImplementedError`）

- [ ] **Step 3: `detect_image` / `summarize` を実装**（検出ルール・集約ルールに従う。`map_score_label_to_tier` を使用。rating 順序は `_RATING_ORDER = {"PG":0,"PG-13":1,"R":2,"X":3,"XXX":4}` を定義）
- [ ] **Step 4: テスト green 確認**
- [ ] **Step 5: mypy + format**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync mypy -p lorairo 2>&1 | grep quality_issue_detection_service || echo "no mypy error"
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync ruff format src/lorairo/services/quality_issue_detection_service.py tests/unit/services/test_quality_issue_detection_service.py
```

- [ ] **Step 6: コミット**

```bash
git add src/lorairo/services/quality_issue_detection_service.py tests/unit/services/test_quality_issue_detection_service.py
git commit -m "feat(results): 構造的品質問題検出サービスを実装 (Refs #726)"
```

---

### Task B: ResultsWidget 表示実装（Track B・並列）

**Files:**
- Modify: `src/lorairo/gui/widgets/results_widget.py`（`display` / `clear` 実装）
- Create: `tests/unit/gui/widgets/test_results_widget.py`

**表示構成（Frame 5 準拠、読み取り専用）:**

- **サマリ band**: batch_size / needs_review_count / clean_count / tier 分布 / 検出 issue 総数。`BatchTriageSummary` から描画。
- **issue band**: `summary.issue_counts` の各種別を issue カードとして並べる（種別ラベル + 件数 + 該当 image_id リスト）。0 件の種別は出さない。
- **per-image 行**: `results` を `needs_review` 優先（issue 有→無）でソートして縦に並べる。各行:
  - image_id / uuid（短縮）/ width×height
  - tags（confidence 付き、低 conf は dim クラス。閾値判定ではなく単に最小値側を視覚的に弱める程度）
  - caption（語数表示）
  - canonical_tier ラベル + scorer pills（model: label）
  - canonical_rating + モデル別 rating（不一致は強調）
  - issue バッジ（その行の `issues`）
  - `▸ レビュー` ボタン（クリックで `review_requested.emit(image_id)`、Phase 2b で Annotate 遷移に接続）
- **clear()**: 「ステージングに画像がありません」プレースホルダ表示。

実装は純コード QWidget（動的生成のため .ui 不使用）。既存スタイルは他 widget を踏襲。

- [ ] **Step 1: 失敗するテストを書く**

```python
import pytest

from lorairo.domain.quality_tier import QualityTier
from lorairo.gui.widgets.results_widget import ResultsWidget
from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    ImageTriageResult,
    IssueType,
    RatingView,
    ScorerView,
    TagView,
)


def _result(image_id: int, issues: list[IssueType]) -> ImageTriageResult:
    return ImageTriageResult(
        image_id=image_id,
        uuid="abcd1234",
        width=1024,
        height=1024,
        tags=[TagView(tag="dog", confidence_score=0.9, model_id=1)],
        caption="a dog on grass",
        caption_word_count=4,
        canonical_rating="PG",
        ratings=[RatingView(model="wd-rater", normalized_rating="PG", confidence_score=0.9)],
        canonical_tier=QualityTier.GOOD_QUALITY,
        scorers=[ScorerView(model="aesthetic_shadow_v2", label="aesthetic", tier=QualityTier.BEST_QUALITY)],
        issues=issues,
    )


def _summary() -> BatchTriageSummary:
    return BatchTriageSummary(
        batch_size=2,
        needs_review_count=1,
        clean_count=1,
        issue_counts={IssueType.EMPTY_TAGS: 1},
        tier_distribution={QualityTier.GOOD_QUALITY: 1},
        no_tier_count=1,
    )


def test_display_renders_rows(qapp):
    widget = ResultsWidget()
    results = [_result(10, [IssueType.EMPTY_TAGS]), _result(11, [])]
    widget.display(_summary(), results)
    # 行が image_id 分描画される
    assert widget.findChild(object, "resultsRow_10") is not None
    assert widget.findChild(object, "resultsRow_11") is not None


def test_review_requested_signal_emitted(qapp, qtbot):
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [IssueType.EMPTY_TAGS])])
    button = widget.findChild(object, "resultsReviewButton_10")
    assert button is not None
    with qtbot.waitSignal(widget.review_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args == [10]


def test_needs_review_sorted_first(qapp):
    widget = ResultsWidget()
    clean = _result(11, [])
    bad = _result(10, [IssueType.EMPTY_TAGS])
    widget.display(_summary(), [clean, bad])
    order = widget._row_order()  # 実装が提供する内部順序アクセサ（list[int]）
    assert order.index(10) < order.index(11)


def test_clear_shows_empty_state(qapp):
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])])
    widget.clear()
    assert widget.findChild(object, "resultsRow_10") is None
    assert widget.findChild(object, "resultsEmptyState") is not None
```

- [ ] **Step 2: テスト失敗確認**

```bash
QT_QPA_PLATFORM=offscreen UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/gui/widgets/test_results_widget.py -v --timeout=60
```

Expected: FAIL

- [ ] **Step 3: `display` / `clear` を実装**

要点:
- 各行コンテナの objectName を `resultsRow_{image_id}`、レビューボタンを `resultsReviewButton_{image_id}` にする（テスト・後続が参照）
- `display` は前回描画をクリアしてから再構築（`clear` ヘルパ共通化、ただし `clear()` 公開メソッドは空状態表示）
- `_row_order() -> list[int]` を内部アクセサとして提供
- 空状態プレースホルダの objectName は `resultsEmptyState`
- レビューボタン click → `self.review_requested.emit(image_id)`

- [ ] **Step 4: テスト green 確認**
- [ ] **Step 5: mypy + format**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync mypy -p lorairo 2>&1 | grep results_widget || echo "no mypy error"
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync ruff format src/lorairo/gui/widgets/results_widget.py tests/unit/gui/widgets/test_results_widget.py
```

- [ ] **Step 6: コミット**

```bash
git add src/lorairo/gui/widgets/results_widget.py tests/unit/gui/widgets/test_results_widget.py
git commit -m "feat(results): ResultsWidget 読み取り専用トリアージ表示を実装 (Refs #726)"
```

---

### Task C: MainWindow への結線（Lead・A/B マージ後）

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

**結線内容:**

- `_setup_results_tab()` を追加し、`tabResults` の `labelResultsStub` を削除して `ResultsWidget` を埋め込む（`verticalLayout_results` に addWidget）。`self.results_widget` 属性に保持。
- `QualityIssueDetectionService` を `self.quality_issue_detection_service` として生成（Qt-free、引数なし）。
- `_on_main_tab_changed` に Results タブ分岐を追加: 表示時に
  1. ステージング集合の image_ids を取得（`batchTagAddWidget.get_staging_widget().get_staged_items()` 経由、Phase 1 で確認済みの共有ステージング）
  2. 各 id について `db_manager.get_image_annotations(id)` + 画像メタ（`db_manager` から uuid/width/height）を取得
  3. `service.detect_image` → `service.summarize`
  4. `results_widget.display(summary, results)`（0 件なら `clear()`）
- `results_widget.review_requested` は Phase 2b で接続（本フェーズは `logger.debug` ログのみのハンドラ、または未接続で可）。

- [ ] **Step 1: 統合テスト追加（red）**

```python
from lorairo.gui.widgets.results_widget import ResultsWidget


    def test_results_tab_embeds_results_widget(self, main_window_with_tabs):
        """結果タブに ResultsWidget が常設される"""
        results_tab = main_window_with_tabs.tabResults
        viewer = results_tab.findChild(ResultsWidget)
        assert viewer is not None
        assert main_window_with_tabs.results_widget is viewer

    def test_results_tab_has_no_stub_label(self, main_window_with_tabs):
        """スタブラベルが除去されている"""
        from PySide6.QtWidgets import QLabel
        stub = main_window_with_tabs.tabResults.findChild(QLabel, "labelResultsStub")
        assert stub is None
```

- [ ] **Step 2: 失敗確認 → 実装 → green**（`get_staged_items` の戻り値型・メタ取得 API は実装時に `db_manager` / staging widget で確認。staging が空でも落ちないこと）
- [ ] **Step 3: CI-equivalent filter（GUI スコープ）で検証**

```bash
QT_QPA_PLATFORM=offscreen UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/gui tests/integration/test_main_window_tab_integration.py tests/unit/services/test_quality_issue_detection_service.py -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

- [ ] **Step 4: コミット**

---

### Task D: 全体検証 + PR（Lead）

- [ ] CI-equivalent filter（全体、worktree 環境失敗は CI が SSoT）
- [ ] push + `gh pr create --base epic/gui-wireframes-v11`
- [ ] CI 監視（ScheduleWakeup）→ green なら epic へ squash merge → #726 にコメント

---

## Agent Teams 実行構成

- **Lead（本セッション）**: Task 1（契約コミット）→ Track A/B worktree 作成 + 並列 dispatch → 完了後マージ → Task C/D
- **Track A worktree**: `.agents/worktree/gui-v11-p2-service`（`feat/gui-v11-p2-service`、Task 1 コミットから分岐）
- **Track B worktree**: `.agents/worktree/gui-v11-p2-widget`（`feat/gui-v11-p2-widget`、Task 1 コミットから分岐）
- ファイル disjoint（A: service+test / B: widget+test）→ マージ無衝突。両者とも契約 dataclass を import するのみ。
- 各 Track は自身の test まで green にして commit。Lead が両ブランチをマージ後 Task C（統合）を実行。

## リスクと注意

- **worktree pytest の解決差**: Phase 1 同様、worktree の pytest は main checkout の editable install を見る場合がある。真偽は push 後 CI が SSoT。
- **staging API**: `get_staged_items()` の戻り値型は Task C 着手時に実装確認（image_id の list か dict か）。
- **画像メタ取得**: uuid/width/height の取得 API は `db_manager.get_images_by_ids` 等で Task C 時に確認。
- **rating 順序**: `PG < PG-13 < R < X < XXX`。`XXX` が DB に存在するか Task A で確認（無ければ 4 値）。
