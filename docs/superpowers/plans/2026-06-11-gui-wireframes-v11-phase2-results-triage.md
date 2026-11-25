# GUI Wireframes v11 — Phase 2 Results 読み取り専用トリアージ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wireframes v11 Frame 5「Results」を読み取り専用のアノテーション品質トリアージ画面として実装し、Phase 1 の `tabResults` スタブを置換する。

**Architecture:** Qt 非依存の `QualityIssueDetectionService`(純粋な分類ロジック)と Qt の `ResultsWidget`(表示)を分離し、`MainWindow` が両者を仲介する MVC 構成とする。検出対象は**構造的事実 5 種のみ**とし、閾値は持たない。データソースには共有ステージング集合(Phase 1 で全タブ共有済み)を使用する。

**Tech Stack:** PySide6、pytest-qt、既存の `domain/quality_tier.py` および `domain/score_scaler.py`、`db_manager.get_image_annotations`

---

## 確定スコープ(ユーザー承認済 2026-06-11)

- **読み取り専用トリアージ:** サマリ帯、issue カード、画像ごとの行の「表示」までを実装する。accept/edit/reject アクション、一括承認、永続化は **Phase 2b** へ分離する。
- **検出閾値は持たない:** 低信頼度タグや短いキャプションは issue 化せず、行内にデータとして表示するだけにとどめる。issue 検出は構造的事実の 5 種のみとする。
  1. `EMPTY_TAGS`: tagger 由来の採用タグが 0 件である。
  2. `NO_SCORE`: scorer 出力(`score` / `score_label`)が存在しない。
  3. `UNKNOWN_TIER`: `score_label` が `map_score_label_to_tier` で `None` になる(マッピング未定義、ADR 0028)。
  4. `RATING_DISAGREEMENT`: 複数モデルの `normalized_rating` が一致していない。
  5. `SCORER_DISAGREEMENT`: 複数 scorer の tier が一致していない(`is_unanimous == false` 相当)。
- **`Image.reviewed_at` マイグレーションは Phase 2b で実施する:** accept アクションと同時に追加する。本フェーズでは未使用カラムを足さない(YAGNI)。
- **データソース:** 共有ステージング集合の `image_ids` を使用する(`dataset_state_manager` または staging widget 経由。Export と同じ「有界・可視・名前付き集合」、ADR 0055)。

---

## 背景と既存資産

- 設計: `docs/design/wireframes-v11/wireframes-v11.html` の `data-screen-label="05 Results"`(Frame 5)
- `src/lorairo/domain/quality_tier.py`: `QualityTier(IntEnum)`、`map_score_label_to_tier(model, label) -> QualityTier | None`、`map_manual_score_to_tier`
- `src/lorairo/domain/score_scaler.py`: `calibrate_to_display`、`select_positive_score` など(生値から表示スコアへの変換)
- `db_manager.get_image_annotations(image_id, *, include_rejected=False)` の戻り値辞書:
  - `tags`: `[{id, tag, tag_id, model_id, confidence_score, rejected_at, is_edited_manually, existing, ...}]`
  - `captions`: `[{id, caption, model_id, rejected_at, ...}]`
  - `scores`: `[{id, score, model_id, ...}]`
  - `score_labels`: `[{id, label, model_id, model, ...}]`(ADR 0028: model 名と組)
  - `ratings`: `[{id, raw_rating_value, normalized_rating, model_id, model, source, confidence_score, ...}]`
- Phase 1 スタブ: `MainWindow.ui` の `tabResults`(`labelResultsStub` を内包する `verticalLayout_results`)

---

## ファイル構成

| ファイル | 担当 Track | 内容 |
|---|---|---|
| `src/lorairo/services/quality_issue_detection_service.py` | Lead(契約)+ A | 契約 dataclass と検出ロジックの実装 |
| `tests/unit/services/test_quality_issue_detection_service.py` | A | 検出ロジックのユニットテスト |
| `src/lorairo/gui/widgets/results_widget.py` | Lead(契約)+ B | `ResultsWidget`(表示、純コード QWidget) |
| `tests/unit/gui/widgets/test_results_widget.py` | B | ウィジェット表示テスト(手組み dataclass 入力) |
| `src/lorairo/gui/window/main_window.py` | Lead(C) | `_setup_results_tab` と Results タブ表示時の配線 |
| `tests/integration/test_main_window_tab_integration.py` | Lead(C) | Results 埋め込みの統合テスト |

ファイル集合は Track A、B、C で完全に分離されているため、並列マージ時に競合しない。論理結合は下記の「共有契約」で吸収する。

---

## 共有契約(Lead が Task 1 で先行コミット。Track A/B はこれをインポートするのみ)

`src/lorairo/services/quality_issue_detection_service.py` の冒頭に以下を定義する。

```python
from dataclasses import dataclass, field
from enum import Enum

from lorairo.domain.quality_tier import QualityTier


class IssueType(Enum):
    """構造的品質問題の種別(閾値非依存)。"""

    EMPTY_TAGS = "empty_tags"
    NO_SCORE = "no_score"
    UNKNOWN_TIER = "unknown_tier"
    RATING_DISAGREEMENT = "rating_disagreement"
    SCORER_DISAGREEMENT = "scorer_disagreement"


@dataclass(frozen=True)
class TagView:
    """行表示用のタグ(採用分のみ)。"""

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
    issues: list[IssueType]               # 検出された構造的問題(空なら clean)

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
    no_tier_count: int                    # tier 算出不能(no-score/unknown)の件数


class QualityIssueDetectionService:
    """ステージング集合のアノテーションを構造的品質問題に分類する(Qt-free)。"""

    def detect_image(self, image_id: int, image_meta: dict, annotations: dict) -> ImageTriageResult:
        """1 画像のアノテーションをトリアージする。

        Args:
            image_id: 画像 ID。
            image_meta: ``{"uuid": str|None, "width": int|None, "height": int|None}``。
            annotations: ``db_manager.get_image_annotations`` の戻り(tags/captions/scores/score_labels/ratings)。
        """
        raise NotImplementedError

    def summarize(self, results: list[ImageTriageResult]) -> BatchTriageSummary:
        """画像別結果をバッチサマリに集約する。"""
        raise NotImplementedError
```

`ResultsWidget` の公開 API(Track B が実装し、Track C が呼び出す)は以下のとおりである。

```python
class ResultsWidget(QWidget):
    """Frame 5 · Results 読み取り専用トリアージ表示。objectName = "resultsWidget"。"""

    review_requested = Signal(int)  # image_id(Annotate へ遷移要求。Phase 2b で接続)

    def __init__(self, parent: QWidget | None = None) -> None: ...

    def display(self, summary: BatchTriageSummary, results: list[ImageTriageResult]) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。"""

    def clear(self) -> None:
        """空状態(ステージング 0 件)を表示する。"""
```

---

### Task 1: 共有契約の先行コミット(Lead)

**Files:**
- Create: `src/lorairo/services/quality_issue_detection_service.py`(上記契約。メソッドは `NotImplementedError`)
- Create: `src/lorairo/gui/widgets/results_widget.py`(`display` と `clear` は `pass` のスタブ、契約インポート)

- [ ] **Step 1: 契約ファイルを作成する**(上記「共有契約」のコード全文)
- [ ] **Step 2: `ResultsWidget` スタブを作成する**

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

- [ ] **Step 3: インポートが通ることを確認する**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync python -c "from lorairo.gui.widgets.results_widget import ResultsWidget; from lorairo.services.quality_issue_detection_service import QualityIssueDetectionService, IssueType, ImageTriageResult, BatchTriageSummary; print('ok')"
```

期待結果: `ok` が出力される。

- [ ] **Step 4: コミットする**

```bash
git add src/lorairo/services/quality_issue_detection_service.py src/lorairo/gui/widgets/results_widget.py
git commit -m "feat(results): Phase 2 共有契約 (dataclass + service/widget skeleton) を追加"
```

---

### Task A: `QualityIssueDetectionService` の検出ロジック実装(Track A・並列)

**Files:**
- Modify: `src/lorairo/services/quality_issue_detection_service.py`(`detect_image` および `summarize` の実装)
- Create: `tests/unit/services/test_quality_issue_detection_service.py`

**検出ルール(閾値なし・構造的事実のみ):**

- `EMPTY_TAGS`: 採用タグ(`rejected_at is None`)が 0 件である(`annotations["tags"]` が空、またはすべて却下済み)。
- `NO_SCORE`: `annotations["scores"]` と `annotations["score_labels"]` が両方空である。
- `UNKNOWN_TIER`: いずれかの `score_label` で `map_score_label_to_tier(sl["model"], sl["label"])` が `None` になる。
- `RATING_DISAGREEMENT`: `annotations["ratings"]` の `normalized_rating` について、重複を除いた値が 2 種類以上ある。
- `SCORER_DISAGREEMENT`: `score_label` を tier へマッピングした結果(`None` を除く)について、重複を除いた値が 2 種類以上ある。

**集約ルール:**

- `canonical_rating`: `ratings` の `normalized_rating` のうち最も厳しい値を採用する(順序は `PG < PG-13 < R < X < XXX`)。
- `canonical_tier`: scorer tier(`None` を除く)の中央値を採用する。偶数個の場合は厳しい側(小さい序数)を採用し、その仕様を docstring に明記する。`None` しかない場合は `None` とする。
- `caption_word_count`: 採用キャプション(最初の `rejected_at is None`)を空白で分割した語数とする。キャプションが無い場合は 0 とする。
- `tags`: 採用タグを `TagView` に変換し、信頼度の降順で並べる。

- [ ] **Step 1: 失敗するテストを書く**(各 issue 種別、clean、summarize を網羅し最低 8 ケース)

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

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/services/test_quality_issue_detection_service.py -v --timeout=60
```

期待結果: `NotImplementedError` で失敗する。

- [ ] **Step 3: `detect_image` と `summarize` を実装する**(上記の検出ルールと集約ルールに従う。`map_score_label_to_tier` を使用し、rating 順序には `_RATING_ORDER = {"PG":0,"PG-13":1,"R":2,"X":3,"XXX":4}` を定義する)
- [ ] **Step 4: テストが通ることを確認する**
- [ ] **Step 5: mypy とフォーマットを実行する**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync mypy -p lorairo 2>&1 | grep quality_issue_detection_service || echo "no mypy error"
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync ruff format src/lorairo/services/quality_issue_detection_service.py tests/unit/services/test_quality_issue_detection_service.py
```

- [ ] **Step 6: コミットする**

```bash
git add src/lorairo/services/quality_issue_detection_service.py tests/unit/services/test_quality_issue_detection_service.py
git commit -m "feat(results): 構造的品質問題検出サービスを実装 (Refs #726)"
```

---

### Task B: `ResultsWidget` の表示実装(Track B・並列)

**Files:**
- Modify: `src/lorairo/gui/widgets/results_widget.py`(`display` および `clear` の実装)
- Create: `tests/unit/gui/widgets/test_results_widget.py`

**表示構成(Frame 5 準拠、読み取り専用):**

- **サマリ帯:** `BatchTriageSummary` に基づき、`batch_size`、`needs_review_count`、`clean_count`、tier 分布、検出 issue 総数を描画する。
- **issue 帯:** `summary.issue_counts` の各種別を issue カードとして並べる(種別ラベル、件数、該当 `image_id` リスト)。0 件の種別は表示しない。
- **画像ごとの行:** `results` を `needs_review` 優先(issue ありから issue なしの順)でソートして縦に並べる。各行には以下を表示する。
  - `image_id`、短縮した `uuid`、`width×height`
  - タグ(信頼度付き。低信頼度のタグは dim クラスで視覚的に弱めるが、閾値判定ではなく最小値側を弱める程度とする)
  - キャプション(語数を表示)
  - `canonical_tier` ラベルと scorer ピル(`model: label`)
  - `canonical_rating` とモデル別 rating(不一致がある場合は強調表示)
  - issue バッジ(その行の `issues`)
  - `▸ レビュー` ボタン(クリック時に `review_requested.emit(image_id)` を発行し、Phase 2b で Annotate 遷移へ接続する)
- **`clear()`:** 「ステージングに画像がありません」のプレースホルダを表示する。

動的生成を行うため、`.ui` ファイルは使わず純粋なコードによる `QWidget` として実装する。既存スタイルは他ウィジェットを踏襲する。

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
    order = widget._row_order()  # 実装が提供する内部順序アクセサ(list[int])
    assert order.index(10) < order.index(11)


def test_clear_shows_empty_state(qapp):
    widget = ResultsWidget()
    widget.display(_summary(), [_result(10, [])])
    widget.clear()
    assert widget.findChild(object, "resultsRow_10") is None
    assert widget.findChild(object, "resultsEmptyState") is not None
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
QT_QPA_PLATFORM=offscreen UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/gui/widgets/test_results_widget.py -v --timeout=60
```

期待結果: 失敗する。

- [ ] **Step 3: `display` と `clear` を実装する**

実装の要点は以下のとおりである。
- 各行コンテナの `objectName` を `resultsRow_{image_id}`、レビューボタンを `resultsReviewButton_{image_id}` とする(テストおよび後続実装から参照される)。
- `display` は前回描画をクリアしてから再構築する。クリア用ヘルパを共通化するが、公開メソッドの `clear()` は空状態を表示する。
- `_row_order() -> list[int]` を内部アクセサとして提供する。
- 空状態プレースホルダの `objectName` は `resultsEmptyState` とする。
- レビューボタンのクリックで `self.review_requested.emit(image_id)` を発行する。

- [ ] **Step 4: テストが通ることを確認する**
- [ ] **Step 5: mypy とフォーマットを実行する**

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync mypy -p lorairo 2>&1 | grep results_widget || echo "no mypy error"
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync ruff format src/lorairo/gui/widgets/results_widget.py tests/unit/gui/widgets/test_results_widget.py
```

- [ ] **Step 6: コミットする**

```bash
git add src/lorairo/gui/widgets/results_widget.py tests/unit/gui/widgets/test_results_widget.py
git commit -m "feat(results): ResultsWidget 読み取り専用トリアージ表示を実装 (Refs #726)"
```

---

### Task C: `MainWindow` への結線(Lead・A/B マージ後)

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

**結線内容:**

- `_setup_results_tab()` を追加し、`tabResults` の `labelResultsStub` を削除して `ResultsWidget` を `verticalLayout_results` へ埋め込む。生成したインスタンスは `self.results_widget` 属性に保持する。
- `QualityIssueDetectionService` を `self.quality_issue_detection_service` として生成する(Qt 非依存、引数なし)。
- `_on_main_tab_changed` に Results タブの分岐を追加し、表示時に以下を実行する。
  1. ステージング集合の `image_ids` を取得する(`batchTagAddWidget.get_staging_widget().get_staged_items()` 経由、Phase 1 で確認済みの共有ステージング)。
  2. 各 ID について `db_manager.get_image_annotations(id)` と画像メタ情報(`db_manager` から uuid、width、height)を取得する。
  3. `service.detect_image` を実行し、`service.summarize` で集約する。
  4. `results_widget.display(summary, results)` を呼び出す(0 件の場合は `clear()`)。
- `results_widget.review_requested` は Phase 2b で接続する。本フェーズでは `logger.debug` のみを出力するハンドラを接続するか、未接続のままとする。

- [ ] **Step 1: 統合テストを追加する(red)**

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

- [ ] **Step 2: 失敗確認から実装、テスト通過までを進める**(`get_staged_items` の戻り値型とメタ取得 API は実装時に `db_manager` と staging widget で確認する。ステージングが空でも例外が出ないことを保証する)
- [ ] **Step 3: CI 相当フィルタ(GUI スコープ)で検証する**

```bash
QT_QPA_PLATFORM=offscreen UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest tests/unit/gui tests/integration/test_main_window_tab_integration.py tests/unit/services/test_quality_issue_detection_service.py -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

- [ ] **Step 4: コミットする**

---

### Task D: 全体検証と PR(Lead)

- [ ] CI 相当フィルタで全体を検証する(ワークツリー環境特有の失敗がある場合は CI を信頼源とする)
- [ ] プッシュし、`gh pr create --base epic/gui-wireframes-v11` で PR を作成する
- [ ] CI を監視(`ScheduleWakeup`)し、すべて通れば epic ブランチへスカッシュマージして #726 にコメントする

---

## Agent Teams 実行構成

- **Lead(本セッション):** Task 1(契約コミット)を実行した後、Track A と B のワークツリーを作成して並列ディスパッチする。両者の完了後にマージし、Task C と D を進める。
- **Track A ワークツリー:** `.agents/worktree/gui-v11-p2-service`(ブランチ `feat/gui-v11-p2-service`、Task 1 コミットから分岐)
- **Track B ワークツリー:** `.agents/worktree/gui-v11-p2-widget`(ブランチ `feat/gui-v11-p2-widget`、Task 1 コミットから分岐)
- Track A(サービスとテスト)と Track B(ウィジェットとテスト)はファイルが完全に分離されているため、マージ競合は発生しない。両者とも契約 dataclass をインポートするのみである。
- 各 Track は自身のテストを通した状態でコミットする。Lead が両ブランチをマージした後、Task C(統合)を実行する。

## リスクと注意

- **ワークツリーでの pytest 解決差:** Phase 1 と同様、ワークツリーからの pytest はメインチェックアウトの editable install を参照する場合がある。最終的な正否はプッシュ後の CI を信頼源とする。
- **staging API:** `get_staged_items()` の戻り値型(`image_id` のリストか辞書か)は Task C 着手時に実装を確認する。
- **画像メタ取得:** uuid、width、height の取得 API は Task C 時に `db_manager.get_images_by_ids` などで確認する。
- **rating 順序:** 順序は `PG < PG-13 < R < X < XXX` とする。`XXX` が DB に存在するかは Task A で確認し、存在しなければ 4 値とする。
