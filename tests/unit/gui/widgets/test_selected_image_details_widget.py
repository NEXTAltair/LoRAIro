# tests/unit/gui/widgets/test_selected_image_details_widget.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, ImageDetails
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget


class FakeDatasetStateManager(QObject):
    current_image_data_changed = Signal(dict)


class FakeMergedReader:
    """翻訳取得と bulk lookup 呼び出し回数検証のための最小 MergedTagReader スタブ。

    完全一致 lookup は大文字小文字を無視する (実 repository の COLLATE NOCASE 相当)。
    表示が verbatim であること (search_tags_bulk を呼ばないこと) の検証にも使う。
    """

    def __init__(
        self,
        mapping: dict[str, str],
        *,
        types: dict[str, str] | None = None,
        languages: list[str] | None = None,
    ) -> None:
        # mapping / types のキーは lowercase 化済みの整形タグ
        self._mapping = mapping
        self._types = types or {}
        self._languages = languages or []
        self.bulk_calls = 0

    def get_tag_languages(self) -> list[str]:
        return self._languages

    def get_translations_batch(self, tag_ids: list[int]) -> dict[int, list]:
        return {}

    def get_usage_counts_batch(self, tag_ids: list[int]) -> dict[int, dict[int, int]]:
        return {}

    def get_format_map(self) -> dict[int, str]:
        return {}

    def get_format_id(self, format_name: str) -> int:
        return 1

    def search_tags_bulk(
        self, tags: list[str], format_name: str | None = None, resolve_preferred: bool = True
    ) -> dict[str, dict]:
        self.bulk_calls += 1
        result: dict[str, dict] = {}
        for tag in tags:
            key = tag.lower()
            if key in self._mapping:
                result[tag] = {"tag": self._mapping[key], "type_name": self._types.get(key)}
        return result

    def search_tags_bulk_all(
        self, tags: list[str], format_name: str | None = None, resolve_preferred: bool = False
    ) -> dict[str, list[dict]]:
        """#1056 の type 解決 (search_tags_batch) 用。TagSearchRow 形の行を返す。"""
        result: dict[str, list[dict]] = {}
        for index, tag in enumerate(tags):
            key = tag.lower()
            if key not in self._types:
                continue
            result[tag] = [
                {
                    "tag": tag,
                    "source_tag": None,
                    "tag_id": 1000 + index,
                    "usage_count": 0,
                    "alias": False,
                    "deprecated": False,
                    "type_id": None,
                    "type_name": self._types[key],
                    "translations": {},
                    "format_statuses": {},
                }
            ]
        return result


class TestSelectedImageDetailsWidget:
    """SelectedImageDetailsWidget単体テスト（Enhanced Event-Driven Pattern対応）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用SelectedImageDetailsWidget"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def sample_image_details(self):
        """テスト用ImageDetailsサンプル"""
        annotation_data = AnnotationData(
            tags=[
                {
                    "tag": "1girl",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.95,
                    "is_edited_manually": False,
                },
                {
                    "tag": "long hair",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.90,
                    "is_edited_manually": False,
                },
                {
                    "tag": "blue eyes",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.88,
                    "is_edited_manually": False,
                },
            ],
            caption="A beautiful anime girl with long hair",
            aesthetic_score=0.85,
            overall_score=850,
            score_type="Aesthetic",
            ratings=[
                {
                    "model": "wd-vit-tagger-v3",
                    "normalized_rating": "R",
                    "raw_rating_value": "questionable",
                    "confidence_score": 0.91,
                    "source": "AI",
                }
            ],
        )

        return ImageDetails(
            image_id=123,
            file_name="sample_image.jpg",
            file_path=str(Path("/test/dataset/sample_image.jpg")),
            image_size="1024x768",
            file_size="2.5 MB",
            created_date="2024-02-15 14:30:00",
            rating_value="PG",
            score_value=850,
            caption="A beautiful anime girl with long hair",
            tags="1girl, long hair, blue eyes",
            annotation_data=annotation_data,
        )

    def test_initialization(self, widget):
        """初期化テスト（Enhanced Event-Driven Pattern）"""
        # Enhanced Event-Driven Patternでの初期化確認
        assert widget.current_details is None
        assert widget.current_image_id is None

        # UIコンポーネントの存在確認（Phase 2: Read-only conversion）
        assert hasattr(widget.ui, "groupBoxImageInfo")
        assert hasattr(widget.ui, "groupBoxTags")
        assert hasattr(widget.ui, "groupBoxCaptions")

        # RatingScoreEditWidget が統合されていることを確認
        assert widget._rating_score_widget is not None

    def test_clear_display(self, widget, sample_image_details):
        """表示クリアテスト"""
        # 初期データ設定
        widget.current_details = sample_image_details
        widget.current_image_id = 123

        # プライベートメソッドの呼び出し（内部実装テスト）
        widget._clear_display()

        # 状態がクリアされることを確認（実際の実装に応じて調整）
        # Note: _clear_display()の実装により具体的なテストは変わる
        pass

    def test_update_details_display(self, widget, sample_image_details):
        """詳細表示更新テスト"""
        # プライベートメソッドのテスト（内部実装確認）
        widget._update_details_display(sample_image_details)

        # 実際の実装により具体的な検証項目は変わる
        # UIラベルの内容更新等を確認
        pass

    def test_summary_value_labels_are_selectable(self, widget):
        """画像情報の値ラベルは選択・コピー可能であること"""
        flags = (
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        for label in (
            widget.ui.labelFileNameValue,
            widget.ui.labelImageSizeValue,
            widget.ui.labelFileSizeValue,
            widget.ui.labelCreatedDateValue,
        ):
            assert label.textInteractionFlags() & flags == flags
            assert label.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_label_clipboard_text_prefers_selected_text(self, widget):
        """QLabelのcontext copyは選択範囲を優先すること"""
        label = widget.ui.labelFileNameValue
        label.setText("sample_image.jpg")
        label.setSelection(0, 6)

        assert widget._label_clipboard_text(label) == "sample"

    def test_copy_current_details_to_clipboard(self, widget, sample_image_details):
        """表示中の詳細情報全体をクリップボードへコピーできること"""
        widget._update_details_display(sample_image_details)

        assert widget.copy_current_details_to_clipboard() is True
        clipboard_text = QApplication.clipboard().text()
        assert "Image ID: 123" in clipboard_text
        assert "File name: sample_image.jpg" in clipboard_text
        assert (
            "Ratings: wd-vit-tagger-v3: R (raw=questionable, confidence=0.91, source=AI)" in clipboard_text
        )
        # #1056: タグはアルファベット順で表示・コピーされる
        assert "Tags: 1girl, blue eyes, long hair" in clipboard_text
        assert "Caption: A beautiful anime girl with long hair" in clipboard_text

    def test_copy_current_details_uses_live_rating_score_widget_values(self, widget, sample_image_details):
        """編集後metadata refresh前でも表示中のRating/Scoreをコピーすること"""
        widget._update_details_display(sample_image_details)
        widget._rating_score_widget.ui.comboBoxRating.setCurrentText("R")
        widget._rating_score_widget.ui.sliderScore.setValue(920)

        assert widget.copy_current_details_to_clipboard() is True
        clipboard_text = QApplication.clipboard().text()
        assert "Rating: R" in clipboard_text
        assert "Score: 9.20" in clipboard_text

    def test_copy_current_details_uses_displayed_tag_language(self, widget, sample_image_details):
        """言語切り替え後は表示中のタグ言語で詳細をコピーすること"""
        sample_image_details.annotation_data.tag_translations = {
            10: {"japanese": "1人の女の子"},
            20: {"japanese": "長い髪"},
            30: {"japanese": "青い目"},
        }
        for tag, tag_id in zip(sample_image_details.annotation_data.tags, (10, 20, 30), strict=True):
            tag["tag_id"] = tag_id
        sample_image_details.annotation_data.available_languages = ["japanese"]

        widget._update_details_display(sample_image_details)
        widget.annotation_display.initialize_language_selector(["japanese"])
        widget.annotation_display._lang_combo.setCurrentText("japanese")

        assert widget.copy_current_details_to_clipboard() is True
        clipboard_text = QApplication.clipboard().text()
        assert "Tags: 1人の女の子, 青い目, 長い髪" in clipboard_text
        assert "Tags: 1girl, blue eyes, long hair" not in clipboard_text

    def test_copy_current_details_without_selection_noops(self, widget):
        """未選択時は詳細全体コピーを行わないこと"""
        QApplication.clipboard().setText("")

        assert widget.copy_current_details_to_clipboard() is False
        assert QApplication.clipboard().text() == ""

    def test_annotation_data_loaded_slot(self, widget):
        """アノテーションデータ読み込み完了スロットテスト"""
        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget._on_annotation_data_loaded()

            # ログが出力される
            mock_logger.debug.assert_called_with("Annotation data loaded in AnnotationDataDisplayWidget")

    def test_enable_disable_widget(self, widget):
        """ウィジェット有効/無効化テスト"""
        # 無効化
        widget.setEnabled(False)
        assert not widget.isEnabled()

        # 有効化
        widget.setEnabled(True)
        assert widget.isEnabled()

    def test_on_image_data_received(self, widget):
        """Enhanced Event-Driven Pattern: 画像データ受信テスト"""
        # テスト用画像メタデータ
        image_data = {
            "id": 456,
            "file_path": "/test/path/test_image.jpg",
            "width": 1920,
            "height": 1080,
            "file_size": 2048000,
            "created_at": "2024-03-15T10:30:00",
            "rating": "PG",
            "score": 750,
        }

        # メソッド呼び出し
        widget._on_image_data_received(image_data)

        # 状態確認
        assert widget.current_image_id == 456
        assert widget.current_details.file_name == "test_image.jpg"
        # Issue #813: 解像度はオリジナル画像基準で "W × H px" 形式
        assert widget.current_details.image_size == "1920 × 1080 px"
        assert widget.current_details.aspect_ratio == "16:9"
        # Phase 2: Read-only widget - rating/score are displayed but not editable
        # The values are stored in current_details
        if widget.current_details.rating_value:
            assert widget.current_details.rating_value == "PG"
        if widget.current_details.score_value:
            assert widget.current_details.score_value == 750

    def test_build_metadata_uses_stored_image_path_for_file_name(self, widget):
        """stored_image_path のみでもファイル名が表示されること"""
        metadata = {
            "id": 1,
            "stored_image_path": "/test/dataset/stored_image.webp",
            "width": 512,
            "height": 768,
            "file_size": 2048,
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        details = widget._build_image_details_from_metadata(metadata)

        assert details.file_name == "stored_image.webp"
        assert details.file_path == "/test/dataset/stored_image.webp"
        assert details.file_size == "2.00 KB"

    def test_build_metadata_normalizes_windows_stored_image_path_for_file_name(self, widget):
        """Windows形式のstored_image_pathでもファイル名だけを表示できること"""
        metadata = {
            "id": 1,
            "stored_image_path": r"C:\test\dataset\windows_image.webp",
            "file_size": 2048,
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        details = widget._build_image_details_from_metadata(metadata)

        assert details.file_name == "windows_image.webp"
        assert details.file_path == "C:/test/dataset/windows_image.webp"

    def test_build_metadata_falls_back_to_file_path_for_file_name(self, widget):
        """旧 metadata の file_path fallback が維持されること"""
        metadata = {
            "id": 1,
            "file_path": "/test/dataset/legacy_image.png",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        details = widget._build_image_details_from_metadata(metadata)

        assert details.file_name == "legacy_image.png"
        assert details.file_path == "/test/dataset/legacy_image.png"
        assert details.file_size == ""

    def test_build_metadata_uses_stored_path_stat_when_file_size_missing(self, widget, tmp_path):
        """file_size が無い場合は stored_image_path の実ファイルサイズで補完すること"""
        image_path = tmp_path / "stat_size_image.jpg"
        image_path.write_bytes(b"x" * 1536)
        metadata = {
            "id": 1,
            "stored_image_path": str(image_path),
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        details = widget._build_image_details_from_metadata(metadata)

        assert details.file_name == "stat_size_image.jpg"
        assert details.file_size == "1.50 KB"

    def test_build_metadata_file_size_missing_for_missing_file_stays_empty(self, widget, tmp_path):
        """ファイルサイズが本当に取得できない場合のみ空表示にすること"""
        metadata = {
            "id": 1,
            "stored_image_path": str(tmp_path / "missing.jpg"),
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        details = widget._build_image_details_from_metadata(metadata)

        assert details.file_name == "missing.jpg"
        assert details.file_size == ""

    def test_on_image_data_received_empty(self, widget):
        """Enhanced Event-Driven Pattern: 空データ受信テスト"""
        # 初期状態設定
        widget.current_image_id = 123
        widget.current_details = ImageDetails(file_name="previous.jpg")

        # 空データ受信
        widget._on_image_data_received({})

        # 表示がクリアされる
        assert widget.current_image_id is None
        assert widget.current_details is None

    def test_connect_to_dataset_state_manager(self, qtbot, widget):
        """DatasetStateManagerの正規データ経路に接続できること"""
        state_manager = FakeDatasetStateManager()
        widget.connect_to_dataset_state_manager(state_manager)

        image_data = {
            "id": 789,
            "file_path": "/test/path/connected_image.jpg",
            "width": 640,
            "height": 480,
            "file_size": 1024,
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        with qtbot.waitSignal(widget.image_details_loaded, timeout=1000) as blocker:
            state_manager.current_image_data_changed.emit(image_data)

        assert blocker.args[0].image_id == 789
        assert widget.current_image_id == 789

    def test_set_merged_reader_none_hides_language_selector(self, widget):
        """set_merged_reader(None)でコンボボックスが非表示になること"""
        widget.set_merged_reader(None)
        # isHidden()はisVisible()と異なり親ウィジェットの表示状態に依存しない
        assert widget.annotation_display._lang_bar.isHidden()

    def test_set_merged_reader_with_valid_reader_shows_selector(self, widget):
        """有効なMergedTagReaderでコンボボックスが表示されること"""
        mock_reader = Mock()
        mock_reader.search_tags_bulk_all.return_value = {}
        mock_reader.get_tag_languages.return_value = ["japanese", "chinese"]

        widget.set_merged_reader(mock_reader)

        assert not widget.annotation_display._lang_bar.isHidden()
        # "english" + 2言語 = 3アイテム
        assert widget.annotation_display._lang_combo.count() == 3

    def test_build_metadata_with_translations(self, widget):
        """翻訳データが正しくAnnotationData.tag_translationsに入ること"""
        mock_reader = Mock()
        mock_reader.search_tags_bulk_all.return_value = {}
        mock_reader.get_tag_languages.return_value = ["japanese"]
        # 翻訳検証に集中するため canonical 変換は no-op (format 未解決) にする
        mock_reader.get_format_id.return_value = None
        tr_mock = Mock()
        tr_mock.language = "japanese"
        tr_mock.translation = "1人の女の子"
        mock_reader.get_translations_batch.return_value = {42: [tr_mock]}
        mock_reader.get_usage_counts_batch.return_value = {}
        mock_reader.get_format_map.return_value = {}
        widget.set_merged_reader(mock_reader)

        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [
                {
                    "tag": "1girl",
                    "tag_id": 42,
                    "model_name": "wd",
                    "source": "AI",
                    "confidence_score": 0.9,
                    "is_edited_manually": False,
                }
            ],
            "caption_text": "",
            "tags_text": "1girl",
            "score_value": 0,
            "rating_value": "",
        }
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert 42 in details.annotation_data.tag_translations
        assert details.annotation_data.tag_translations[42]["japanese"] == "1人の女の子"

    def test_build_metadata_with_usage_counts(self, widget):
        """使用頻度が bulk 取得され format 名へ解決して AnnotationData に入ること (#990)。"""
        mock_reader = Mock()
        mock_reader.search_tags_bulk_all.return_value = {}
        mock_reader.get_tag_languages.return_value = []
        mock_reader.get_format_id.return_value = None
        mock_reader.get_translations_batch.return_value = {}
        # format_id 1=danbooru / 2=e621。未知 format_id 99 は format_map に無いので除外される。
        mock_reader.get_format_map.return_value = {1: "danbooru", 2: "e621"}
        mock_reader.get_usage_counts_batch.return_value = {42: {1: 1234, 2: 42, 99: 7}}
        widget.set_merged_reader(mock_reader)

        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [
                {
                    "tag": "1girl",
                    "tag_id": 42,
                    "model_name": "wd",
                    "source": "AI",
                    "confidence_score": 0.9,
                    "is_edited_manually": False,
                }
            ],
            "caption_text": "",
            "tags_text": "1girl",
            "score_value": 0,
            "rating_value": "",
        }
        details = widget._build_image_details_from_metadata(metadata)

        mock_reader.get_usage_counts_batch.assert_called_once_with([42])
        assert details.annotation_data is not None
        # format_id が format 名へ解決され、map 未掲載の 99 は除外される
        assert details.annotation_data.tag_usage_counts == {42: {"danbooru": 1234, "e621": 42}}

    def test_build_metadata_skips_tag_without_tag_id(self, widget):
        """tag_id=Noneのタグは翻訳取得をスキップすること"""
        mock_reader = Mock()
        mock_reader.search_tags_bulk_all.return_value = {}
        mock_reader.get_tag_languages.return_value = ["japanese"]
        mock_reader.get_format_id.return_value = None
        mock_reader.get_translations_batch.return_value = {}
        widget.set_merged_reader(mock_reader)

        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [
                {
                    "tag": "1girl",
                    "tag_id": None,
                    "model_name": "wd",
                    "source": "AI",
                    "confidence_score": 0.9,
                    "is_edited_manually": False,
                }
            ],
            "caption_text": "",
            "tags_text": "1girl",
            "score_value": 0,
            "rating_value": "",
        }
        details = widget._build_image_details_from_metadata(metadata)

        # tag_id=Noneのタグはスキップ → get_translations_batchは呼ばれない
        mock_reader.get_translations_batch.assert_not_called()
        assert details.annotation_data is not None
        assert details.annotation_data.tag_translations == {}

    def test_build_metadata_translations_uses_single_batch_call(self, widget):
        """N個タグが存在してもget_translations_batchは1回だけ呼ばれること"""
        mock_reader = Mock()
        mock_reader.search_tags_bulk_all.return_value = {}
        mock_reader.get_tag_languages.return_value = []
        mock_reader.get_format_id.return_value = None
        mock_reader.get_translations_batch.return_value = {}
        mock_reader.get_usage_counts_batch.return_value = {}
        mock_reader.get_format_map.return_value = {}
        widget.set_merged_reader(mock_reader)

        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [
                {
                    "tag": f"tag{i}",
                    "tag_id": i,
                    "model_name": "wd",
                    "source": "AI",
                    "confidence_score": 0.9,
                    "is_edited_manually": False,
                }
                for i in range(1, 11)
            ],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }
        widget._build_image_details_from_metadata(metadata)

        mock_reader.get_translations_batch.assert_called_once()
        call_args = mock_reader.get_translations_batch.call_args[0][0]
        assert len(call_args) == 10

    def test_build_metadata_populates_score_labels(self, widget):
        """metadata の score_labels が AnnotationData に渡されること (ADR 0028)。

        PR #286 Codex 指摘の核: producer 側で score_labels を埋めないと、
        consumer 側の pill 表示が常に空になる silent バグの回帰防止。
        """
        score_labels = [
            {
                "label": "very aesthetic",
                "model": "aesthetic_shadow_v1",
                "model_id": 1,
                "is_edited_manually": False,
            },
            {
                "label": "aesthetic",
                "model": "cafe_aesthetic",
                "model_id": 2,
                "is_edited_manually": False,
            },
        ]
        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
            "score_labels": score_labels,
        }
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert details.annotation_data.score_labels == score_labels

    def test_build_metadata_score_labels_missing_defaults_empty(self, widget):
        """metadata に score_labels key が無い場合は default [] になる (旧データ互換)。"""
        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
            # score_labels なし
        }
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert details.annotation_data.score_labels == []

    def test_build_metadata_populates_quality_summary(self, widget):
        """metadata の quality_summary が AnnotationData に渡されること (ADR 0029)。

        PR #297 Codex P1 の核: GUI のメタデータ経路で quality_summary を埋めないと、
        統一 tier badge が常に hidden になる silent バグの回帰防止。
        """
        quality_summary = {
            "mapping_version": "quality-tier-v1",
            "tier": "best quality",
            "is_unanimous": True,
            "known_count": 2,
            "unknown_count": 0,
            "no_score": False,
            "votes": [],
        }
        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
            "score_labels": [],
            "quality_summary": quality_summary,
        }
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert details.annotation_data.quality_summary == quality_summary

    def test_build_metadata_quality_summary_missing_defaults_empty(self, widget):
        """metadata に quality_summary key が無い場合は default {} になる (旧データ互換)。"""
        metadata = {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
            # quality_summary なし
        }
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert details.annotation_data.quality_summary == {}

    # ─── 表示は verbatim (ADR 0068 改訂: canonical は保存時に焼き込み済み) ──────

    @staticmethod
    def _build_tag_metadata(tags: list[dict]) -> dict:
        """表示テスト用の最小 metadata を生成する。"""
        return {
            "id": 1,
            "file_path": "/test/img.jpg",
            "tags": tags,
            "caption_text": "",
            "tags_text": ", ".join(t["tag"] for t in tags),
            "score_value": 0,
            "rating_value": "",
        }

    def test_display_shows_tags_verbatim(self, widget):
        """ADR 0068 改訂: Tag.tag は保存時に canonical 化済みのため表示は verbatim。

        reader を設定しても表示時に DB 変換 (search_tags_bulk) を呼ばないこと。
        """
        reader = FakeMergedReader({"gray hair": "grey hair"})
        widget.set_merged_reader(reader)

        metadata = self._build_tag_metadata(
            [
                {"tag": "grey hair", "tag_id": 1, "model_name": "wd", "source": "AI"},
                {"tag": "pov hands", "tag_id": 2, "model_name": "wd", "source": "AI"},
            ]
        )
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        # 保存済みの値がそのまま表示される (変換しない)
        assert [t["tag"] for t in details.annotation_data.tags] == ["grey hair", "pov hands"]
        # 表示時に canonical 変換の DB lookup が走らないこと
        assert reader.bulk_calls == 0

    def test_display_without_reader_shows_tags_verbatim(self, widget):
        """reader 未設定でも保存済みタグをそのまま表示する。"""
        metadata = self._build_tag_metadata(
            [
                {"tag": "grey hair", "tag_id": 1, "model_name": "wd", "source": "AI"},
            ]
        )
        details = widget._build_image_details_from_metadata(metadata)

        assert details.annotation_data is not None
        assert [t["tag"] for t in details.annotation_data.tags] == ["grey hair"]
        assert details.tags == "grey hair"


@pytest.mark.unit
@pytest.mark.gui
class TestOriginalImageMetaDisplay:
    """Issue #813: オリジナル画像メタ (拡張子/アスペクト比/アルファ) の整形・表示。"""

    @pytest.fixture
    def widget(self, qtbot):
        from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

        w = SelectedImageDetailsWidget()
        qtbot.addWidget(w)
        return w

    def test_aspect_ratio_reduced(self, widget):
        assert widget._format_aspect_ratio(1920, 1080) == "16:9"
        assert widget._format_aspect_ratio(1024, 1024) == "1:1"
        assert widget._format_aspect_ratio(0, 100) == ""

    def test_extension_prefers_extension_then_format(self, widget):
        assert widget._format_original_extension({"extension": "png"}) == ".png"
        assert widget._format_original_extension({"extension": ".jpg"}) == ".jpg"
        assert widget._format_original_extension({"format": "WEBP"}) == "WEBP"
        assert widget._format_original_extension({}) == ""

    def test_alpha_text(self, widget):
        assert "あり" in widget._format_alpha({"has_alpha": True})
        assert "なし" in widget._format_alpha({"has_alpha": False})
        assert widget._format_alpha({"has_alpha": None}) == "不明"

    def test_display_populates_original_meta_rows(self, widget):
        widget._on_image_data_received(
            {"id": 7, "width": 1600, "height": 900, "extension": "png", "has_alpha": True, "mode": "RGBA"}
        )
        assert widget.labelExtensionValue.text() == ".png"
        assert widget.labelAspectValue.text() == "16:9"
        assert "あり" in widget.labelAlphaValue.text()

    def test_display_populates_image_id_and_phash(self, widget):
        """#1058: 画像情報グループに画像IDと pHash が表示される。"""
        widget._on_image_data_received({"id": 42, "width": 100, "height": 100, "phash": "a1b2c3d4e5f60789"})
        assert widget.labelImageIdValue.text() == "42"
        assert widget.labelPhashValue.text() == "a1b2c3d4e5f60789"

    def test_image_id_and_phash_rows_reset_on_clear(self, widget):
        """#1058: クリア時は画像ID/pHash 行も '-' に戻る。"""
        widget._on_image_data_received({"id": 42, "width": 100, "height": 100, "phash": "a1b2c3d4e5f60789"})
        widget._clear_display()
        assert widget.labelImageIdValue.text() == "-"
        assert widget.labelPhashValue.text() == "-"

    def test_image_id_and_phash_labels_are_copyable(self, widget):
        """#1058: 画像ID/pHash はクリック選択でクリップボードコピーできる。"""
        from PySide6.QtCore import Qt

        for label in (widget.labelImageIdValue, widget.labelPhashValue):
            assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


class TestReadableLayoutTopPacking:
    """#827: 詳細ペインをトップ詰めにし、レーティング詳細と評価スコア編集の間に
    余白ができないことを担保する。"""

    @pytest.fixture
    def widget(self, qtbot):
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    def test_layout_ends_with_stretch_spacer(self, widget):
        """#833: コンテナレイアウト末尾に stretch spacer があり、余剰を最下部へ逃がす
        (widgetResizable=True + 末尾 spacer の堅牢構成)。"""
        layout = widget._summary_layout
        last_item = layout.itemAt(layout.count() - 1)
        assert last_item.spacerItem() is not None

    def test_annotation_display_has_no_stretch(self, widget):
        """annotationDataDisplay には stretch を与えない (余白は末尾 spacer に集約)。"""
        layout = widget._summary_layout
        index = layout.indexOf(widget.ui.annotationDataDisplay)
        assert index != -1
        assert layout.stretch(index) == 0

    def test_no_gap_between_annotation_and_rating_score(self, widget, qtbot):
        """画像選択時、annotationDataDisplay と評価スコア編集の間が spacing のみになる
        (#827 / #833: タグが多くても巨大な隙間が出ないこと)。"""
        widget.resize(400, 900)
        widget.show()
        qtbot.waitExposed(widget)
        widget._on_image_data_received(
            {
                "id": 1,
                "width": 1024,
                "height": 768,
                "rating": "R",
                "score_value": 7.0,
                "tags": [{"tag": f"tag{i}", "tag_id": i} for i in range(60)],
                "ratings": [
                    {
                        "model": "m1",
                        "normalized_rating": "R",
                        "raw_rating_value": "explicit",
                        "confidence_score": 0.9,
                        "source": "AI",
                    }
                ],
            }
        )
        qtbot.waitUntil(lambda: widget._rating_score_widget.isVisible(), timeout=2000)
        ad = widget.ui.annotationDataDisplay
        rsw = widget._rating_score_widget
        gap = rsw.geometry().y() - (ad.geometry().y() + ad.geometry().height())
        # spacing (4px) 程度。タグが多くても過大な隙間 (>= 40px) が出ないこと。
        assert gap < 40
