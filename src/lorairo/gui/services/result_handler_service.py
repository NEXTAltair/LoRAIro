"""結果処理サービス

Worker/Service実行結果の処理とUI通知を担当。
MainWindowの結果ハンドラメソッドから抽出（Phase 2.4 Stage 2）。
"""

from typing import Any

from loguru import logger
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox, QWidget


class ResultHandlerService:
    """結果処理サービス

    Worker/Serviceの実行結果を処理し、UIに通知する責務を担当。
    MainWindowから分離し、結果処理ロジックを集約。

    
    """

    def __init__(self, parent: QWidget | None = None):
        """初期化

        Args:
            parent: 親ウィジェット（QMessageBox用、Noneも可）
        """
        self.parent = parent

    def handle_batch_registration_finished(
        self, result: Any, status_bar: Any | None = None, completion_signal: Signal | None = None
    ) -> None:
        """バッチ登録完了処理

        Args:
            result: バッチ登録結果（DatabaseRegistrationResult）
            status_bar: ステータスバー（showMessage()メソッドを持つ）
            completion_signal: 完了シグナル（emit()で通知）
        """
        logger.info(f"バッチ登録完了: result={type(result)}")

        # Clear statusbar processing message
        try:
            if status_bar:
                status_bar.clearMessage()
        except Exception as e:
            logger.debug(f"Status bar clear failed: {e}")

        try:
            # Extract results from DatabaseRegistrationResult
            if hasattr(result, "registered_count"):
                registered = result.registered_count
                skipped = result.skipped_count
                errors = result.error_count
                processing_time = result.total_processing_time

                # Emit completion signal for other components
                if completion_signal:
                    completion_signal.emit(registered)

                # 非ブロッキング通知でUIクラッシュを防止
                status_msg = f"バッチ登録完了: 登録={registered}件, スキップ={skipped}件, エラー={errors}件, 処理時間={processing_time:.1f}秒"
                if status_bar:
                    status_bar.showMessage(status_msg, 8000)  # 8秒表示
                logger.info(f"バッチ登録統計: 登録={registered}, スキップ={skipped}, エラー={errors}")

            else:
                # Fallback for unexpected result format
                logger.warning(f"Unexpected batch registration result format: {result}")
                # 非ブロッキング通知でUIクラッシュを防止
                if status_bar:
                    status_bar.showMessage("バッチ登録完了（詳細情報取得不可）", 5000)

        except Exception as e:
            # Proper error logging instead of silent failure
            logger.error(f"バッチ登録完了処理中にエラー: {e}", exc_info=True)
            # 非ブロッキング通知でUIクラッシュを防止
            if status_bar:
                status_bar.showMessage(f"バッチ登録完了（結果表示エラー: {str(e)[:50]}）", 5000)

    def handle_batch_annotation_finished(self, result: Any, status_bar: Any | None = None) -> None:
        """バッチアノテーション完了処理

        Args:
            result: バッチアノテーション結果（BatchAnnotationResult）
            status_bar: ステータスバー（showMessage()メソッドを持つ）
        """
        try:
            # BatchAnnotationResult属性にアクセス
            total = getattr(result, "total_images", 0)
            successful = getattr(result, "successful_annotations", 0)
            failed = getattr(result, "failed_annotations", 0)
            success_rate = getattr(result, "success_rate", 0.0)
            summary = getattr(result, "summary", "バッチ処理完了")

            logger.info(f"バッチアノテーション完了: {summary}")

            # ステータスバー表示（成功率を含む）
            status_msg = f"完了: {successful}件成功, {failed}件失敗 (成功率: {success_rate:.1f}%)"
            if status_bar:
                status_bar.showMessage(status_msg, 10000)

            # 成功時の通知（完了メッセージ）
            if self.parent:
                if failed == 0:
                    # 全て成功
                    QMessageBox.information(
                        self.parent,
                        "アノテーション完了",
                        f"アノテーション処理が正常に完了しました。\n\n"
                        f"処理画像数: {total}件\n"
                        f"成功: {successful}件",
                    )
                else:
                    # 一部失敗
                    QMessageBox.warning(
                        self.parent,
                        "アノテーション完了（一部エラー）",
                        f"アノテーション処理が完了しましたが、一部にエラーがありました。\n\n"
                        f"処理画像数: {total}件\n"
                        f"成功: {successful}件\n"
                        f"失敗: {failed}件\n"
                        f"成功率: {success_rate:.1f}%\n\n"
                        "詳細はログを確認してください。",
                    )

        except Exception as e:
            logger.error(f"バッチ完了ハンドラエラー: {e}", exc_info=True)
            if self.parent:
                QMessageBox.critical(self.parent, "処理エラー", f"結果処理中にエラーが発生しました:\n{e}")

    def handle_annotation_finished(self, result: Any, status_bar: Any | None = None) -> None:
        """単発アノテーション完了処理

        Args:
            result: アノテーション結果
            status_bar: ステータスバー（showMessage()メソッドを持つ）
        """
        try:
            logger.info(f"アノテーション完了: {result}")
            if status_bar:
                status_bar.showMessage("アノテーション処理が完了しました", 5000)

        except Exception as e:
            logger.error(f"アノテーション完了ハンドラエラー: {e}", exc_info=True)

    def handle_annotation_error(self, error_msg: str, status_bar: Any | None = None) -> None:
        """アノテーションエラー処理

        Args:
            error_msg: エラーメッセージ
            status_bar: ステータスバー（showMessage()メソッドを持つ）
        """
        try:
            logger.error(f"アノテーションエラー: {error_msg}")
            if status_bar:
                status_bar.showMessage(f"エラー: {error_msg}", 8000)

            # ユーザーへの詳細エラー通知
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "アノテーション処理エラー",
                    f"アノテーション処理中にエラーが発生しました:\n\n{error_msg}\n\n"
                    "APIキーの設定やネットワーク接続を確認してください。",
                )

        except Exception as e:
            logger.error(f"エラーハンドラで予期しない例外: {e}", exc_info=True)

    def handle_model_sync_completed(self, sync_result: Any, status_bar: Any | None = None) -> None:
        """モデル同期完了処理

        Args:
            sync_result: モデル同期結果
            status_bar: ステータスバー（showMessage()メソッドを持つ）
        """
        try:
            logger.info(f"モデル同期完了: {sync_result}")

            # 同期成功通知
            if hasattr(sync_result, "success") and sync_result.success:
                summary = getattr(sync_result, "summary", "モデル同期完了")
                if status_bar:
                    status_bar.showMessage(f"モデル同期完了: {summary}", 5000)
            else:
                # 同期失敗
                errors = getattr(sync_result, "errors", [])
                error_msg = ", ".join(errors) if errors else "不明なエラー"
                if status_bar:
                    status_bar.showMessage(f"モデル同期エラー: {error_msg}", 8000)
                logger.error(f"モデル同期エラー: {error_msg}")

        except Exception as e:
            logger.error(f"モデル同期完了ハンドラエラー: {e}", exc_info=True)
