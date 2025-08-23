# tests/unit/gui/workers/test_progress_helper.py

import pytest

from lorairo.gui.workers.progress_helper import ProgressHelper


class TestProgressHelper:
    """ProgressHelper共通ユーティリティのテスト"""

    def test_calculate_percentage_basic(self):
        """基本的な進捗パーセンテージ計算テスト"""
        # 50% 進捗
        result = ProgressHelper.calculate_percentage(5, 10)
        assert result == 50

        # 100% 進捗
        result = ProgressHelper.calculate_percentage(10, 10)
        assert result == 100

        # 0% 進捗
        result = ProgressHelper.calculate_percentage(0, 10)
        assert result == 0

    def test_calculate_percentage_with_range(self):
        """範囲指定付き進捗パーセンテージ計算テスト"""
        # 10-90%の範囲で50%進捗（結果: 50%）
        result = ProgressHelper.calculate_percentage(5, 10, 10, 80)
        assert result == 50

        # 20-100%の範囲で25%進捗（結果: 40%）
        result = ProgressHelper.calculate_percentage(1, 4, 20, 80)
        assert result == 40

    def test_calculate_percentage_zero_total(self):
        """総数が0の場合の処理テスト"""
        result = ProgressHelper.calculate_percentage(0, 0)
        assert result == 100

        result = ProgressHelper.calculate_percentage(0, 0, 10, 80)
        assert result == 90

    def test_get_batch_boundaries_basic(self):
        """基本的なバッチ境界計算テスト"""
        # 10アイテムを3つのバッチに分割
        boundaries = ProgressHelper.get_batch_boundaries(10, 3)
        expected = [(0, 3), (3, 6), (6, 9), (9, 10)]
        assert boundaries == expected

    def test_get_batch_boundaries_exact_division(self):
        """きっかり分割できる場合のテスト"""
        # 9アイテムを3つのバッチに分割
        boundaries = ProgressHelper.get_batch_boundaries(9, 3)
        expected = [(0, 3), (3, 6), (6, 9)]
        assert boundaries == expected

    def test_get_batch_boundaries_edge_cases(self):
        """エッジケースのテスト"""
        # アイテム数0
        boundaries = ProgressHelper.get_batch_boundaries(0, 3)
        assert boundaries == []

        # バッチサイズ0
        boundaries = ProgressHelper.get_batch_boundaries(10, 0)
        assert boundaries == []

        # バッチサイズがアイテム数より大きい
        boundaries = ProgressHelper.get_batch_boundaries(5, 10)
        expected = [(0, 5)]
        assert boundaries == expected

    def test_create_batch_reporter(self):
        """バッチレポーター生成テスト"""
        # 100アイテムで50回報告
        should_report = ProgressHelper.create_batch_reporter(100, 50)

        # 2間隔で報告すべき
        assert should_report(0) is True   # 0 % 2 == 0
        assert should_report(1) is False  # 1 % 2 != 0
        assert should_report(2) is True   # 2 % 2 == 0

    def test_create_batch_reporter_edge_cases(self):
        """バッチレポーター生成エッジケースのテスト"""
        # アイテム数0
        should_report = ProgressHelper.create_batch_reporter(0, 50)
        assert should_report(1) is False

        # 小さなアイテム数
        should_report = ProgressHelper.create_batch_reporter(3, 50)
        # 最小間隔は1
        assert should_report(0) is True
        assert should_report(1) is True
        assert should_report(2) is True

    def test_create_time_throttled_checker(self):
        """時間スロットリング制御生成テスト"""
        import time

        # 100ms間隔
        should_report = ProgressHelper.create_time_throttled_checker(100)

        # 最初は必ず報告
        assert should_report() is True

        # すぐ次は報告しない
        assert should_report() is False

        # 少し待つと報告する
        time.sleep(0.11)  # 110ms待機
        assert should_report() is True

    def test_create_combined_throttle(self):
        """組み合わせスロットリング生成テスト"""
        # 10アイテムで5回報告、100ms間隔
        should_report = ProgressHelper.create_combined_throttle(10, 5, 100)

        # バッチ条件（2間隔）と時間条件の両方が必要
        # 最初は時間条件でTrue
        first_result = should_report(0)  # 0 % 2 == 0 かつ 初回時間チェックTrue
        assert first_result is True
