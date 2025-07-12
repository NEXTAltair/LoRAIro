"""
タイムゾーン扱いのテスト

_parse_datetime_str メソッドがUTC統一方針に従って正しく動作することを確認します。
"""

import datetime
from datetime import UTC

import pytest

from lorairo.database.db_core import DefaultSessionLocal
from lorairo.database.db_repository import ImageRepository


class TestTimezoneHandling:
    """タイムゾーン扱いのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.repository = ImageRepository(session_factory=DefaultSessionLocal)

    def test_parse_datetime_str_with_valid_iso_format(self):
        """有効なISO形式の日付文字列のテスト"""
        # ISO 8601形式（Tセパレータ）
        result = self.repository._parse_datetime_str("2024-01-15T10:30:00")

        # 結果がUTC timezone-aware datetimeであることを確認
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 0
        assert result.tzinfo == UTC

    def test_parse_datetime_str_with_space_separator(self):
        """スペース区切りの日付文字列のテスト"""
        # スペース区切り形式
        result = self.repository._parse_datetime_str("2024-01-15 10:30:00")

        # 結果がUTC timezone-aware datetimeであることを確認
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 0
        assert result.tzinfo == UTC

    def test_parse_datetime_str_with_microseconds(self):
        """マイクロ秒を含む日付文字列のテスト"""
        # マイクロ秒を含む形式（削除される）
        result = self.repository._parse_datetime_str("2024-01-15T10:30:00.123456")

        # マイクロ秒は削除されることを確認
        assert result is not None
        assert result.microsecond == 0
        assert result.tzinfo == UTC

    def test_parse_datetime_str_with_timezone_info(self):
        """タイムゾーン情報を含む日付文字列のテスト"""
        # UTCタイムゾーン情報を含む形式
        result = self.repository._parse_datetime_str("2024-01-15T10:30:00+00:00")

        # 元々のタイムゾーン情報が保持されることを確認
        assert result is not None
        assert result.tzinfo is not None
        # UTC+0なので結果的にUTCと同じ時刻

    def test_parse_datetime_str_with_empty_string(self):
        """空文字列のテスト"""
        result = self.repository._parse_datetime_str("")
        assert result is None

    def test_parse_datetime_str_with_none(self):
        """None値のテスト"""
        result = self.repository._parse_datetime_str(None)
        assert result is None

    def test_parse_datetime_str_with_invalid_format(self):
        """無効な形式の日付文字列のテスト"""
        # 無効な形式
        result = self.repository._parse_datetime_str("invalid-date")
        assert result is None

    def test_parse_datetime_str_with_date_only(self):
        """日付のみの文字列のテスト"""
        # 日付のみ（時刻なし）
        result = self.repository._parse_datetime_str("2024-01-15")

        # 時刻は00:00:00になることを確認
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.tzinfo == UTC

    def test_timezone_consistency_with_db_comparison(self):
        """データベースとの比較時のタイムゾーン一貫性テスト"""
        # パースされた日時がデータベースの TIMESTAMP(timezone=True) と比較可能であることを確認
        parsed_dt = self.repository._parse_datetime_str("2024-01-15T10:30:00")

        # UTCのaware datetimeであることを確認
        assert parsed_dt is not None
        assert parsed_dt.tzinfo is not None
        assert parsed_dt.tzinfo == UTC

        # 現在時刻（UTC）との比較が可能であることを確認
        now_utc = datetime.datetime.now(UTC)
        assert isinstance(parsed_dt, datetime.datetime)
        assert isinstance(now_utc, datetime.datetime)
        # 比較演算子が正常に動作することを確認（例外が発生しない）
        comparison_result = parsed_dt < now_utc
        assert isinstance(comparison_result, bool)

    def teardown_method(self):
        """各テストメソッドの後に実行されるクリーンアップ処理"""
        pass


if __name__ == "__main__":
    pytest.main([__file__])
