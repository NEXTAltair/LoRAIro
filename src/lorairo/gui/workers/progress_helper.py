# src/lorairo/gui/workers/progress_helper.py

import time
from collections.abc import Callable


class ProgressHelper:
    """進捗管理のための共通ユーティリティクラス
    
    コード重複を削減し、一貫性のある進捗管理を提供します。
    """

    @staticmethod
    def calculate_percentage(current: int, total: int, base: int = 0, range_value: int = 100) -> int:
        """進捗パーセンテージ計算の統一
        
        Args:
            current: 現在の処理数
            total: 総処理数
            base: ベースパーセンテージ（開始点）
            range_value: パーセンテージ範囲
            
        Returns:
            計算されたパーセンテージ
        """
        if total == 0:
            return base + range_value
        return base + int((current / total) * range_value)

    @staticmethod
    def create_batch_reporter(total_items: int, target_reports: int = 50) -> Callable[[int], bool]:
        """バッチ進捗レポーター生成
        
        Args:
            total_items: 総アイテム数
            target_reports: 目標報告回数
            
        Returns:
            現在位置で報告すべきかを判定する関数
        """
        if total_items == 0:
            return lambda current: False

        interval = max(1, total_items // target_reports)
        return lambda current: current % interval == 0

    @staticmethod
    def create_time_throttled_checker(min_interval_ms: int = 50) -> Callable[[], bool]:
        """時間ベーススロットリング制御生成
        
        Args:
            min_interval_ms: 最小報告間隔（ミリ秒）
            
        Returns:
            報告すべきかを時間基準で判定する関数
        """
        last_report_time = [0]  # mutable reference for closure

        def should_report() -> bool:
            current_time = time.monotonic_ns() // 1_000_000
            if current_time - last_report_time[0] >= min_interval_ms:
                last_report_time[0] = current_time
                return True
            return False

        return should_report

    @staticmethod
    def create_combined_throttle(
        total_items: int,
        target_reports: int = 50,
        min_interval_ms: int = 50
    ) -> Callable[[int], bool]:
        """バッチ + 時間制御の組み合わせ
        
        Args:
            total_items: 総アイテム数
            target_reports: 目標報告回数
            min_interval_ms: 最小報告間隔（ミリ秒）
            
        Returns:
            現在位置と時間の両方を考慮した判定関数
        """
        batch_checker = ProgressHelper.create_batch_reporter(total_items, target_reports)
        time_checker = ProgressHelper.create_time_throttled_checker(min_interval_ms)

        return lambda current: batch_checker(current) and time_checker()

    @staticmethod
    def get_batch_boundaries(total_items: int, batch_size: int) -> list[tuple[int, int]]:
        """バッチ境界の計算
        
        Args:
            total_items: 総アイテム数
            batch_size: バッチサイズ
            
        Returns:
            (start_idx, end_idx) のタプルリスト
        """
        if total_items == 0 or batch_size <= 0:
            return []

        boundaries = []
        for start_idx in range(0, total_items, batch_size):
            end_idx = min(start_idx + batch_size, total_items)
            boundaries.append((start_idx, end_idx))
        return boundaries
