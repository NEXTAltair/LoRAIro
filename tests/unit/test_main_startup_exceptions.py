"""起動経路 (``lorairo.main``) の except の絞り込みテスト (#1610)。

継続してよい既知の例外では起動を続け、想定外の例外は握らず上位ハンドラへ伝播する
ことを確かめる。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtGui import QFontDatabase

from lorairo import main as main_module


class _UnexpectedStartupError(Exception):
    """絞り込んだ例外型のどれにも当たらない、想定外の例外。"""


@pytest.mark.unit
class TestSetupApplicationFonts:
    """setup_application_fonts の except は設定値の不正・Qt API 失敗だけを継続扱いにする。"""

    @pytest.mark.parametrize(
        ("config", "exception_name"),
        [
            pytest.param({"qt": "not-a-table"}, "AttributeError", id="qt-section-not-dict"),
            pytest.param({"qt": {"font_size": "large"}}, "TypeError", id="font-size-wrong-type"),
            pytest.param({"qt": {"font_size": 2**40}}, "OverflowError", id="font-size-int-overflow"),
            pytest.param({"qt": {"font_size": float("inf")}}, "OverflowError", id="font-size-inf"),
            pytest.param({"qt": {"font_size": float("nan")}}, "OverflowError", id="font-size-nan"),
            pytest.param(
                {"qt": {"font_size": -(2**40)}}, "OverflowError", id="font-size-negative-overflow"
            ),
        ],
    )
    def test_invalid_font_config_is_logged_and_startup_continues(
        self, qapp, config: dict[str, Any], exception_name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warnings: list[str] = []
        monkeypatch.setattr(
            main_module.logger, "warning", lambda message, *a, **k: warnings.append(message)
        )
        monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda *a, **k: ["DejaVu Sans"]))

        main_module.setup_application_fonts(qapp, config)

        assert any("フォント設定でエラー" in message for message in warnings), exception_name

    def test_qt_runtime_error_is_logged_and_startup_continues(
        self, qapp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args: Any, **_kwargs: Any) -> list[str]:
            raise RuntimeError("font db unavailable")

        monkeypatch.setattr(QFontDatabase, "families", staticmethod(_raise))

        main_module.setup_application_fonts(qapp, {})

    def test_unexpected_exception_propagates(self, qapp, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*_args: Any, **_kwargs: Any) -> list[str]:
            raise _UnexpectedStartupError

        monkeypatch.setattr(QFontDatabase, "families", staticmethod(_raise))

        with pytest.raises(_UnexpectedStartupError):
            main_module.setup_application_fonts(qapp, {})


def _run_main_with_hidden_window(
    monkeypatch: pytest.MonkeyPatch, show_error: Exception
) -> tuple[int, Mock, Mock]:
    """ウィンドウが表示されず強制表示が失敗する状況で ``main()`` を最後まで走らせる。

    Returns:
        (終了コード, 起動エラーダイアログのモック, MainWindow インスタンスのモック)。
    """
    window = MagicMock()
    window.isVisible.return_value = False
    window.showNormal.side_effect = show_error
    app = MagicMock()
    app.exec.return_value = 0
    show_critical = Mock()

    monkeypatch.setattr(main_module, "parse_arguments", lambda: Mock(debug=False))
    monkeypatch.setattr(main_module, "get_config", lambda: {"log": {}})
    monkeypatch.setattr(main_module, "setup_qt_environment", Mock())
    monkeypatch.setattr(main_module, "initialize_logging", Mock())
    monkeypatch.setattr(main_module, "build_gui_log_config", Mock())
    monkeypatch.setattr(main_module, "QApplication", Mock(return_value=app))
    monkeypatch.setattr(main_module, "setup_application_fonts", Mock())
    monkeypatch.setattr(main_module.theme, "apply_theme", Mock())
    monkeypatch.setattr(main_module, "MainWindow", Mock(return_value=window))
    monkeypatch.setattr(main_module, "QTimer", Mock())
    monkeypatch.setattr(main_module, "show_critical", show_critical)
    monkeypatch.setattr("genai_tag_db_tools.set_query_abort_check", Mock())

    return main_module.main(), show_critical, window


@pytest.mark.unit
class TestForceShowWindow:
    """ウィンドウ強制表示の except は Qt の既知の失敗だけを継続扱いにする。"""

    @pytest.mark.parametrize("exception_type", [AttributeError, RuntimeError])
    def test_known_failure_continues_startup(
        self, exception_type: type[Exception], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exit_code, show_critical, window = _run_main_with_hidden_window(
            monkeypatch, exception_type("cannot show")
        )

        assert exit_code == 0
        show_critical.assert_not_called()
        window.start_tag_db_warmup.assert_called_once_with()

    def test_unexpected_failure_reaches_startup_error_dialog(self, monkeypatch: pytest.MonkeyPatch) -> None:
        exit_code, show_critical, window = _run_main_with_hidden_window(
            monkeypatch, _UnexpectedStartupError("bug")
        )

        assert exit_code == 1
        show_critical.assert_called_once()
        window.start_tag_db_warmup.assert_not_called()
