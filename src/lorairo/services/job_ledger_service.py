"""In-memory job ledger service (ADR 0066 Unified Jobs Lifecycle View).

同期ジョブ (Pipeline / Operation レベル, ADR 0034) のセッションスコープ台帳。
ADR 0066 §2 に従い DB 永続化はしない (アプリ再起動で消える)。
Provider Batch は既存 ``provider_batch_jobs`` テーブルが SSoT のため本台帳には載せない。

Qt-free: GUI への変更通知は WorkerService (Qt 層) が ``job_ledger_changed``
シグナルとして担う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# ADR 0066 §5 / Issue #754: model installer 用 job_type。
# OperationType.MODEL_INSTALL (gui/services/operation_events.py) と同値で、
# 未インストールモデルの明示ダウンロードジョブが本台帳に載る。
JOB_TYPE_MODEL_INSTALL = "model_install"

# DS v12 JobsScreen (Issue #805): 集計の「過去N日完了」窓。
_DONE_WINDOW_DAYS = 7

# Issue #805: アノテーション capability → DS JobsScreen のステージ表示ラベル。
# capability 文字列は供給元で揺れがある (Codex P2): annotator_adapter は複数形
# ("tags"/"captions"/"scores"/"ratings"/"score_labels")、model_registry_protocol /
# pipeline_composition は単数形 ("caption"/"score"/"rating") を使う。両方を吸収する。
_CAPABILITY_STAGE_LABELS: dict[str, str] = {
    "tag": "TAGS",
    "tags": "TAGS",
    "caption": "CAPTION",
    "captions": "CAPTION",
    "score": "SCORE",
    "scores": "SCORE",
    "score_label": "SCORE",
    "score_labels": "SCORE",
    "rating": "RATING",
    "ratings": "RATING",
}
# ステージ表示順 (DS JobsScreen の per-stage カードの並び)。
_STAGE_ORDER: tuple[str, ...] = ("TAGS", "CAPTION", "SCORE", "RATING", "ANNOTATE")
# capability 不明モデルのフォールバックステージ。
_FALLBACK_STAGE = "ANNOTATE"


class JobStatus(Enum):
    """Ledger-visible lifecycle status of one job (ADR 0066 §1)."""

    RUNNING = "running"
    QUEUED = "queued"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def is_terminal(self) -> bool:
        """終端状態 (履歴セクション行き) かどうかを返す。"""
        return self in {JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED}


@dataclass
class StageProgress:
    """実行中ジョブのステージ (アノテーション種別) 別進捗 (Issue #805 / DS JobsScreen)。

    DS の per-stage ProgressBar カード 1 行ぶんに対応する。すべて実データ由来で、
    捏造値は持たない (集計不能な値は ``percentage=0`` / ``detail=""`` で表す)。

    Attributes:
        stage: ステージ表示ラベル ("TAGS" / "CAPTION" / "SCORE" / "RATING" / "ANNOTATE")。
        model_name: 表示モデル名。
        meta: 補助メタ ("OpenAI · api" / "local" 等、provider + 経路)。
        percentage: 進捗率 (0-100)。処理済み画像数 / 総数から算出。
        detail: 右端の done テキスト ("6 / 9" / "失敗" 等)。
        tone: 表示トーン ("ok" 完了 / "info" 実行中 / "err" 失敗)。
    """

    stage: str
    model_name: str
    meta: str
    percentage: int
    detail: str
    tone: str


@dataclass
class StageModelInput:
    """``build_stage_progress`` に渡す 1 モデルぶんの入力 (Qt-free, Issue #805)。

    Worker が ``ModelRegistryServiceProtocol`` から解決した情報を詰める軽量 DTO。

    Attributes:
        key: 完了/失敗の追跡に使う一意キー (litellm_model_id)。同一 ``model_name``
            に解決する別ルート (direct / OpenRouter 等) を取り違えないため、表示名
            ではなくこのキーで進捗状態を引く。
        model_name: 表示モデル名 (重複し得る、表示専用)。
        provider: provider 名 ("openai" / "local" 等)。
        capabilities: capability 文字列リスト。
        requires_api_key: API キー要否 (経路 api / local 判定用)。
    """

    key: str
    model_name: str
    provider: str
    capabilities: list[str]
    requires_api_key: bool


@dataclass
class JobsSummary:
    """Jobs サマリ帯 (SummaryStat) 用の集計値 (Issue #805 / DS JobsScreen)。

    すべて in-memory 台帳 (session-scoped) の実データから算出する。台帳に無い指標
    (provider API レート使用量等) は本 dataclass には含めず、UI 側で「データなし」を
    正直に表示する。

    Attributes:
        running: 実行中 (RUNNING) のジョブ数。
        queued: 待機中 (QUEUED) のジョブ数。
        done_7d: 過去 7 日以内に正常完了 (FINISHED) したジョブ数。
        failed_7d: 過去 7 日以内に失敗 (FAILED) したジョブ数。
    """

    running: int
    queued: int
    done_7d: int
    failed_7d: int


@dataclass
class JobEntry:
    """One ledger row for a sync job (session-scoped, in-memory)."""

    job_id: str
    job_type: str
    title: str
    status: JobStatus = JobStatus.RUNNING
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    summary: str = ""
    # Issue #805: 実行中ジョブのステージ別進捗 (terminal 後は据え置き、UI は実行中のみ表示)。
    stage_progress: list[StageProgress] = field(default_factory=list)


def build_stage_progress(
    models: list[StageModelInput],
    *,
    processed_count: int,
    total_count: int,
    finished: bool = False,
    completed_keys: set[str] | None = None,
    errored_keys: set[str] | None = None,
) -> list[StageProgress]:
    """選択モデル群から DS JobsScreen 用のステージ別進捗を構築する (Qt-free)。

    各モデルを capability ごとのステージ行に展開する。進捗率は処理済み画像数 /
    総数の実値から算出し、捏造しない。完了/失敗の判定は表示名ではなく一意キー
    (``StageModelInput.key`` = litellm_model_id) で行うため、同一表示名へ解決する
    別ルートを取り違えない。

    Args:
        models: 選択モデルの入力 DTO リスト (選択順)。
        processed_count: 処理済み画像数 (現時点)。完了/未完了の区別は
            ``completed_keys`` で行い、未完了モデルはこの値由来の率で描く。
        total_count: 対象画像総数。
        finished: アノテーション完了済みなら True (全ステージを 100% / ok で表示)。
        completed_keys: 個別に完了済みのモデルキー集合 (per-model fallback 用)。
        errored_keys: 失敗したモデルキー集合 (per-model fallback 用)。

    Returns:
        ステージ表示順 (TAGS→CAPTION→SCORE→RATING→ANNOTATE) に並べた進捗行リスト。
    """
    completed = completed_keys or set()
    errored = errored_keys or set()
    running_pct = _ratio_to_percentage(processed_count, total_count)
    detail_progress = f"{processed_count} / {total_count}" if total_count > 0 else ""
    detail_done = f"{total_count} / {total_count}" if total_count > 0 else "完了"

    rows: list[StageProgress] = []
    for model in models:
        meta = _format_model_meta(model.provider, model.requires_api_key)
        for stage in _stages_for_capabilities(model.capabilities):
            if model.key in errored:
                rows.append(StageProgress(stage, model.model_name, meta, 0, "失敗", "err"))
            elif finished or model.key in completed:
                rows.append(StageProgress(stage, model.model_name, meta, 100, detail_done, "ok"))
            else:
                rows.append(
                    StageProgress(stage, model.model_name, meta, running_pct, detail_progress, "info")
                )
    rows.sort(
        key=lambda row: _STAGE_ORDER.index(row.stage) if row.stage in _STAGE_ORDER else len(_STAGE_ORDER)
    )
    return rows


def _ratio_to_percentage(processed: int, total: int) -> int:
    """処理済み / 総数を 0-100 のパーセンテージに変換する。"""
    if total <= 0:
        return 0
    return max(0, min(100, round(processed / total * 100)))


def _stages_for_capabilities(capabilities: list[str]) -> list[str]:
    """capability 文字列リストを DS ステージラベル列に変換する (重複除去・順序保持)。"""
    stages: list[str] = []
    for capability in capabilities:
        label = _CAPABILITY_STAGE_LABELS.get(capability.strip().lower())
        if label is not None and label not in stages:
            stages.append(label)
    return stages or [_FALLBACK_STAGE]


def _format_model_meta(provider: str, requires_api_key: bool) -> str:
    """provider + 推論経路 (api / local) を DS メタ表記へ整形する。"""
    route = "api" if requires_api_key else "local"
    provider_label = provider.strip()
    if provider_label and provider_label.lower() not in {"local", "unknown"}:
        return f"{provider_label} · {route}"
    return route


class JobLedgerService:
    """In-memory ledger of Pipeline/Operation level jobs (ADR 0066 §2, §3).

    register/update/finish の 3 操作で台帳行を管理する。検索/サムネイル等の
    UI 応答系 Worker は載せない (載せると firehose 化する、ADR 0066 §3)。
    """

    def __init__(self) -> None:
        # 挿入順を保持する dict (Python 3.7+)。表示は新しい順に返す。
        self._entries: dict[str, JobEntry] = {}

    def register(
        self,
        job_id: str,
        job_type: str,
        title: str,
        *,
        status: JobStatus = JobStatus.RUNNING,
    ) -> JobEntry:
        """ジョブを台帳に登録する。

        Args:
            job_id: ジョブ識別子 (worker_id をそのまま使う)。
            job_type: ジョブ種別 ("annotation", "batch_registration" 等)。
            title: 表示タイトル。
            status: 初期状態 (既定 RUNNING。キュー実装時は QUEUED)。

        Returns:
            登録した JobEntry。同一 job_id が既に存在する場合は既存行を返す。
        """
        existing = self._entries.get(job_id)
        if existing is not None:
            return existing
        entry = JobEntry(job_id=job_id, job_type=job_type, title=title, status=status)
        self._entries[job_id] = entry
        return entry

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        summary: str | None = None,
    ) -> JobEntry | None:
        """ジョブの状態・サマリーを更新する。

        Args:
            job_id: 対象ジョブ識別子。
            status: 新しい状態 (None なら据え置き)。
            summary: 新しいサマリー (None なら据え置き)。

        Returns:
            更新後の JobEntry。未登録の job_id なら None。
        """
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        if status is not None:
            entry.status = status
        if summary is not None:
            entry.summary = summary
        return entry

    def finish(self, job_id: str, status: JobStatus, summary: str = "") -> JobEntry | None:
        """ジョブを終端状態にして finished_at を確定する。

        Args:
            job_id: 対象ジョブ識別子。
            status: 終端状態 (FINISHED / FAILED / CANCELED)。
            summary: 結果サマリー (件数・エラーメッセージ等)。

        Returns:
            更新後の JobEntry。未登録の job_id なら None。

        Raises:
            ValueError: 終端でない status が渡された場合。
        """
        if not status.is_terminal:
            raise ValueError(f"finish() requires a terminal status, got: {status.value}")
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        entry.status = status
        entry.summary = summary
        entry.finished_at = datetime.now()
        return entry

    def set_stage_progress(self, job_id: str, stages: list[StageProgress]) -> JobEntry | None:
        """実行中ジョブのステージ別進捗を更新する (Issue #805)。

        Args:
            job_id: 対象ジョブ識別子。
            stages: ステージ別進捗リスト (空可)。

        Returns:
            更新後の JobEntry。未登録の job_id なら None。
        """
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        entry.stage_progress = stages
        return entry

    def summary(self, *, now: datetime | None = None) -> JobsSummary:
        """サマリ帯 (SummaryStat) 用の集計値を返す (Issue #805)。

        Args:
            now: 集計基準時刻 (テスト用に注入可能、既定は現在時刻)。

        Returns:
            running / queued / 過去7日完了・失敗の件数を保持する JobsSummary。
        """
        reference = now or datetime.now()
        window_start = reference - timedelta(days=_DONE_WINDOW_DAYS)
        running = queued = done_7d = failed_7d = 0
        for entry in self._entries.values():
            if entry.status is JobStatus.RUNNING:
                running += 1
            elif entry.status is JobStatus.QUEUED:
                queued += 1
            elif entry.finished_at is not None and entry.finished_at >= window_start:
                if entry.status is JobStatus.FINISHED:
                    done_7d += 1
                elif entry.status is JobStatus.FAILED:
                    failed_7d += 1
        return JobsSummary(running=running, queued=queued, done_7d=done_7d, failed_7d=failed_7d)

    def get(self, job_id: str) -> JobEntry | None:
        """job_id で台帳行を取得する。"""
        return self._entries.get(job_id)

    def list_entries(self) -> list[JobEntry]:
        """全台帳行を新しい順 (登録の逆順) で返す。"""
        return list(reversed(self._entries.values()))

    def running_entries(self) -> list[JobEntry]:
        """非終端 (running / queued) の行を新しい順で返す。"""
        return [entry for entry in self.list_entries() if not entry.status.is_terminal]
