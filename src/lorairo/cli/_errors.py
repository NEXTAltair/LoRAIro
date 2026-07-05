"""CLI 構造化エラー契約 (ADR 0057 §4/§5/§6)。

任意の失敗を安定エラーコード集合と固定 exit code policy に写す。エージェントは
stderr 文字列をパースせずコードとフラグで分岐でき、人間も理由を読める。失敗時の
stdout 最終行は ``{"kind": "error", ...}`` (:func:`lorairo.cli._emit.emit_error`)。

Exit code policy (ADR 0057 §6 / ADR 0060):
    0 = 成功
    2 = 入力・検証 (``INVALID_INPUT`` / ``VALIDATION_FAILED`` / ``RESULT_SET_TOO_LARGE``)
    1 = 実行時 (上記以外すべて)

例外 → コード分類 (:func:`classify_exception`) は 2 つの技法を使う:

- **cause-chain walking**: ``__cause__`` / ``__context__`` を遡り ``raise X from e`` で
  wrap された真因を拾う (LoRAIro は iam-lib 例外を多層 wrap するため必須)。
- **module-prefix matching**: 例外クラスをモジュール名で判定し、分類のために ``torch`` /
  推論 SDK を eager import しない (lazy import 制約、ADR 0010 系)。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """安定 wire エラーコード (全 15 種、ADR 0057 §4)。"""

    # 共有コア 11 種 (tag-db ADR 0003 と共有)
    INVALID_INPUT = "INVALID_INPUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    IO_ERROR = "IO_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    DB_ERROR = "DB_ERROR"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # AI 推論ドメイン拡張 3 種
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    # pagination ドメイン拡張 1 種 (ADR 0060)
    RESULT_SET_TOO_LARGE = "RESULT_SET_TOO_LARGE"


EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_INPUT_ERROR = 2

# 呼び出し側の不正リクエストを表すコード (exit 2)。
_INPUT_CODES = frozenset(
    {ErrorCode.INVALID_INPUT, ErrorCode.VALIDATION_FAILED, ErrorCode.RESULT_SET_TOO_LARGE}
)

# コードごとの短い対処ヒント (任意)。
_HINTS: dict[ErrorCode, str] = {
    ErrorCode.PRECONDITION_FAILED: "先に必要な前提操作 (プロジェクト作成 / 画像登録) を実行してください。",
    ErrorCode.NETWORK_ERROR: "ネットワーク接続を確認して再試行してください。",
    ErrorCode.AUTH_ERROR: "config/lorairo.toml に該当プロバイダの API キーを設定してください。",
    ErrorCode.RESOURCE_EXHAUSTED: "batch_size を下げてから再実行してください (同一条件の再試行は再失敗します)。",
    ErrorCode.RATE_LIMITED: "しばらく待ってから再試行してください。",
    ErrorCode.RESULT_SET_TOO_LARGE: "検索条件を追加して 500 件以下に絞ってください。",
    ErrorCode.CONFLICT: (
        "DB が他プロセス (GUI 等) の書き込みでロックされています。"
        "完了を待ってから再試行してください (SQLite は同時書き込みを 1 つに制限します)。"
    ),
}


@dataclass(frozen=True)
class ErrorInfo:
    """raise された例外の分類結果。

    Args:
        code: 安定エラーコード。
        retryable: 同一/調整後の再試行で成功し得るか (一時的障害か)。
        user_action_required: 再試行前に入力/前提の変更が必要か。
    """

    code: ErrorCode
    retryable: bool
    user_action_required: bool

    @property
    def exit_code(self) -> int:
        """固定 policy に従う process exit code を返す。"""
        return EXIT_INPUT_ERROR if self.code in _INPUT_CODES else EXIT_RUNTIME_ERROR


_DISK_IO_HINT = (
    "SQLite の disk I/O error です。GUI と CLI を別 OS (Windows GUI × コンテナ CLI 等) から"
    "同じ DB に向けていないか確認し、GUI と同一 OS で CLI を実行するか GUI を閉じてください。"
)


def hint_for(code: ErrorCode, exc: BaseException | None = None) -> str | None:
    """コードに対する短い対処ヒントを返す (定義がなければ ``None``)。

    Args:
        code: 分類済みエラーコード。
        exc: 元の例外 (渡されると例外固有のヒントを優先する)。

    Returns:
        対処ヒント文字列、定義がなければ ``None``。
    """
    if exc is not None and code is ErrorCode.IO_ERROR:
        from lorairo.database.db_errors import is_sqlite_disk_io_error

        # クロス OS の WAL -shm 問題 (Issue #1169/#1175) は実行環境の指示を返す
        if is_sqlite_disk_io_error(exc):
            return _DISK_IO_HINT
    return _HINTS.get(code)


def _module_chain_matches(exc: BaseException, prefixes: tuple[str, ...]) -> bool:
    """例外 MRO のいずれかが ``prefixes`` のモジュール由来なら ``True``。"""
    return any(cls.__module__.startswith(prefixes) for cls in type(exc).__mro__)


def _name_in_mro(exc: BaseException, names: frozenset[str]) -> bool:
    """例外 MRO のいずれかのクラス名が ``names`` に含まれれば ``True``。"""
    return any(cls.__name__ in names for cls in type(exc).__mro__)


def _iter_cause_chain(exc: BaseException) -> list[BaseException]:
    """``__cause__`` / ``__context__`` chain を遡る (``raise X from e`` 対応)。

    LoRAIro は iam-lib 例外を ``typer.Exit`` 等で包む多層 wrap が多いため、真因を
    辿らないと download 失敗を precondition と誤分類する。
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


_NETWORK_MODULES = ("requests", "urllib3", "huggingface_hub", "http.client", "httpx")
_NETWORK_NAMES = frozenset(
    {
        "HfHubHTTPError",
        "LocalEntryNotFoundError",
        "OfflineModeIsEnabled",
        "ConnectionError",
        "APIConnectionError",
    }
)
_AUTH_SDK_MODULES = ("anthropic", "openai", "google", "litellm")
_AUTH_NAMES = frozenset({"AuthenticationError", "PermissionDeniedError"})
_RATE_NAMES = frozenset({"RateLimitError"})
_OOM_NAMES = frozenset({"OutOfMemoryError", "ImageLoadMemoryError", "MemoryError"})
_APIKEY_NAMES = frozenset({"APIKeyNotConfiguredError"})


def _matches_network(exc: BaseException) -> bool:
    if _module_chain_matches(exc, _NETWORK_MODULES):
        return True
    return _name_in_mro(exc, _NETWORK_NAMES)


def _is_network_error(exc: BaseException) -> bool:
    return any(_matches_network(item) for item in _iter_cause_chain(exc))


def _is_db_error(exc: BaseException) -> bool:
    return any(_module_chain_matches(item, ("sqlalchemy",)) for item in _iter_cause_chain(exc))


def _is_sqlite_lock(exc: BaseException) -> bool:
    """SQLite の書き込みロック競合 (``database is locked``) かを判定する。

    判定ロジックは GUI ワーカーと共有するため :mod:`lorairo.database.db_errors`
    に集約している (遅延 import で軽量に保つ)。
    """
    from lorairo.database.db_errors import is_sqlite_lock_error

    return is_sqlite_lock_error(exc)


def _is_sqlite_disk_io(exc: BaseException) -> bool:
    """SQLite の ``disk I/O error`` (クロス OS WAL -shm 問題等) かを判定する。"""
    from lorairo.database.db_errors import is_sqlite_disk_io_error

    return is_sqlite_disk_io_error(exc)


def _is_auth_error(exc: BaseException) -> bool:
    for item in _iter_cause_chain(exc):
        # LoRAIro 独自の APIKeyNotConfiguredError (SDK 到達前にキー未設定で送出)
        if _name_in_mro(item, _APIKEY_NAMES):
            return True
        # プロバイダ SDK の AuthenticationError / PermissionDeniedError
        if _name_in_mro(item, _AUTH_NAMES) and _module_chain_matches(item, _AUTH_SDK_MODULES):
            return True
    return False


def _is_rate_limited(exc: BaseException) -> bool:
    return any(
        _name_in_mro(item, _RATE_NAMES) and _module_chain_matches(item, _AUTH_SDK_MODULES)
        for item in _iter_cause_chain(exc)
    )


def _is_resource_exhausted(exc: BaseException) -> bool:
    for item in _iter_cause_chain(exc):
        if _name_in_mro(item, _OOM_NAMES):
            return True
        if isinstance(item, RuntimeError) and "out of memory" in str(item).lower():
            return True
    return False


def _classify_lorairo_exception(exc: BaseException) -> ErrorInfo | None:
    """LoRAIro 独自例外を分類する (該当しなければ ``None``)。

    自前の例外階層は ``lorairo.public_api.exceptions`` 由来 (純 ``Exception`` 派生、torch 等を
    引かず import 安全) なので isinstance で判定する。
    """
    from lorairo.public_api import exceptions as app_exc

    if isinstance(
        exc,
        (
            app_exc.ProjectNotFoundError,
            app_exc.ImageNotFoundError,
            app_exc.TagNotFoundError,
            app_exc.ErrorRecordNotFoundError,
        ),
    ):
        return ErrorInfo(ErrorCode.NOT_FOUND, retryable=False, user_action_required=True)
    if isinstance(exc, (app_exc.ProjectAlreadyExistsError, app_exc.DuplicateImageError)):
        return ErrorInfo(ErrorCode.ALREADY_EXISTS, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.ResultSetTooLargeError):
        return ErrorInfo(ErrorCode.RESULT_SET_TOO_LARGE, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.BatchImportError):
        return ErrorInfo(ErrorCode.VALIDATION_FAILED, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.AnnotationFailedError):
        return ErrorInfo(ErrorCode.PRECONDITION_FAILED, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.InvalidFormatError):
        return ErrorInfo(ErrorCode.INVALID_INPUT, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.ValidationError):
        return ErrorInfo(ErrorCode.VALIDATION_FAILED, retryable=False, user_action_required=True)
    if isinstance(exc, app_exc.DatabaseError):
        return ErrorInfo(ErrorCode.DB_ERROR, retryable=False, user_action_required=False)
    return None


# cause-chain で真因を優先判定する分類器テーブル (順序が結果優先順位、上が勝つ)。
# wrap された OOM / 認証 / ネットワークを真因として拾うため LoRAIro 独自例外より先に評価する。
# SQLite ロックは SQLAlchemy ``OperationalError`` でもあるため、汎用 DB エラーより先に
# 評価して再試行可能な CONFLICT に分類する (Issue #767)。
_CHAIN_CLASSIFIERS: tuple[tuple[Callable[[BaseException], bool], ErrorInfo], ...] = (
    (
        _is_resource_exhausted,
        ErrorInfo(ErrorCode.RESOURCE_EXHAUSTED, retryable=True, user_action_required=True),
    ),
    (_is_auth_error, ErrorInfo(ErrorCode.AUTH_ERROR, retryable=False, user_action_required=True)),
    (_is_rate_limited, ErrorInfo(ErrorCode.RATE_LIMITED, retryable=True, user_action_required=False)),
    (_is_network_error, ErrorInfo(ErrorCode.NETWORK_ERROR, retryable=True, user_action_required=False)),
    (_is_sqlite_lock, ErrorInfo(ErrorCode.CONFLICT, retryable=True, user_action_required=False)),
    # disk I/O error は実行環境の問題 (Issue #1169/#1175) なので DB_ERROR より先に
    # IO_ERROR + user_action_required で分類し、環境ヒント (_DISK_IO_HINT) に繋ぐ
    (
        _is_sqlite_disk_io,
        ErrorInfo(ErrorCode.IO_ERROR, retryable=False, user_action_required=True),
    ),
    (_is_db_error, ErrorInfo(ErrorCode.DB_ERROR, retryable=False, user_action_required=False)),
)


def _classify_standard_exception(exc: BaseException) -> ErrorInfo:
    """標準/Pydantic 例外をフォールバック分類する。

    Pydantic ``ValidationError`` は ``ValueError`` の subclass、``FileNotFoundError`` は
    ``OSError`` の subclass のため、いずれも基底クラスより先に判定する。
    """
    if type(exc).__name__ == "ValidationError" and _module_chain_matches(exc, ("pydantic",)):
        return ErrorInfo(ErrorCode.VALIDATION_FAILED, retryable=False, user_action_required=True)
    if isinstance(exc, TimeoutError):
        return ErrorInfo(ErrorCode.TIMEOUT, retryable=True, user_action_required=False)
    if isinstance(exc, FileNotFoundError):
        return ErrorInfo(ErrorCode.IO_ERROR, retryable=False, user_action_required=True)
    if _name_in_mro(exc, frozenset({"AnnotationSelectionError"})):
        return ErrorInfo(ErrorCode.PRECONDITION_FAILED, retryable=False, user_action_required=True)
    if _name_in_mro(exc, frozenset({"AnnotationRunFailedError"})):
        return ErrorInfo(ErrorCode.PRECONDITION_FAILED, retryable=False, user_action_required=True)
    if isinstance(exc, ValueError):
        return ErrorInfo(ErrorCode.INVALID_INPUT, retryable=False, user_action_required=True)
    if isinstance(exc, OSError):
        return ErrorInfo(ErrorCode.IO_ERROR, retryable=False, user_action_required=True)
    return ErrorInfo(ErrorCode.INTERNAL_ERROR, retryable=False, user_action_required=False)


def classify_exception(exc: BaseException) -> ErrorInfo:
    """raise された例外を安定 :class:`ErrorInfo` に写す。

    順序が重要: cause-chain ベースの判定 (:data:`_CHAIN_CLASSIFIERS`: resource / auth /
    rate / network / db) を先に行い、真因が wrap されていても正しく拾う。次に LoRAIro
    独自例外を isinstance で分類し、最後に標準例外をフォールバックする。

    Args:
        exc: 分類対象の例外。

    Returns:
        コードと再試行/ユーザー操作フラグを持つ :class:`ErrorInfo`。
    """
    for predicate, info in _CHAIN_CLASSIFIERS:
        if predicate(exc):
            return info
    lorairo_info = _classify_lorairo_exception(exc)
    if lorairo_info is not None:
        return lorairo_info
    return _classify_standard_exception(exc)
