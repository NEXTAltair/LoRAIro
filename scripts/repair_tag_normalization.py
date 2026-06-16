"""既存 LoRAIro DB の `tags.tag` を `clean_format` で一括整形する修復スクリプト (Issue #769)。

ADR 0068 の保存境界方針に従い、保存は整形 (`TagCleaner.clean_format().strip()`) のみを
焼き込む。alias→preferred の解決や lower 化は format 依存のため **行わない**。

整形によって同一 `(image_id, model_id)` 内で `tag` 文字列が衝突した行 (例:
`blue_hair_` → `blue hair` が既存の `blue hair` と重複) は、代表行 1 件を残して残りを
削除し、論理的な一意性 `(image_id, model_id, tag)` を保つ。

使い方:
    # dry-run (デフォルト): 変更件数と diff サマリのみ表示、書き込まない
    uv run python scripts/repair_tag_normalization.py --db-path lorairo_data/<project>/image_database.db

    # 実書き込み (事前に DB ファイルのバックアップを取得する)
    uv run python scripts/repair_tag_normalization.py --db-path <path> --apply
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import typer
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from loguru import logger
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.schema import Tag
from lorairo.utils.config import get_config

app = typer.Typer(help="Repair tags.tag normalization in an existing LoRAIro image database.")

# dry-run 時に表示する diff サンプルの最大件数。
_DIFF_SAMPLE_LIMIT = 30


def normalize_tag_value(tag: str) -> str:
    """タグ文字列を保存境界の正規化規則で整形する。

    ADR 0068 に従い `TagCleaner.clean_format()` + `strip()` のみを適用する。
    lower 化や alias/preferred 解決は行わない。

    Args:
        tag: 整形前のタグ文字列。

    Returns:
        整形済みのタグ文字列。整形結果が空になる場合は空文字列。
    """
    # clean_format は @cache + @staticmethod のため戻り値型が Any になる。str に束縛して返す。
    cleaned: str = TagCleaner.clean_format(tag)
    return cleaned.strip()


@dataclass
class TagUpdate:
    """整形により `tag` 値を更新する行の diff 情報。"""

    tag_row_id: int
    image_id: int | None
    model_id: int | None
    old_tag: str
    new_tag: str


@dataclass
class TagDeletion:
    """重複マージ / 空文字整形で削除する行の情報。"""

    tag_row_id: int
    image_id: int | None
    model_id: int | None
    old_tag: str
    new_tag: str
    survivor_row_id: int | None


@dataclass
class RepairPlan:
    """修復スクリプトが算出する変更計画。"""

    updates: list[TagUpdate] = field(default_factory=list)
    duplicate_deletions: list[TagDeletion] = field(default_factory=list)
    empty_deletions: list[TagDeletion] = field(default_factory=list)
    unchanged_count: int = 0
    total_count: int = 0

    @property
    def has_changes(self) -> bool:
        """書き込みが必要な変更が存在するか。"""
        return bool(self.updates or self.duplicate_deletions or self.empty_deletions)


def _survivor_sort_key(row: Tag) -> tuple[int, int, int, int, int, int]:
    """重複行から残す代表行を選ぶためのソートキーを返す。

    タプルの各要素は小さいほど優先 (= 残す) を意味する。保守的に、より多くの
    メタデータを持つ行 / 手動編集された行を残し、最後は最古 (最小 id) を残す。

    優先順位 (高い順):
        1. 手動編集済み (`is_edited_manually` が True)
        2. 外部 tag_db と紐付く (`tag_id` が非 NULL)
        3. confidence_score を持つ (非 NULL)
        4. 元ファイル由来 (`existing` が True)
        5. 未 reject (`rejected_at` が NULL)
        6. id が小さい (最古)

    Args:
        row: 評価対象の Tag 行。

    Returns:
        sorted() に渡すソートキー (昇順で先頭が残す代表行)。
    """
    return (
        0 if row.is_edited_manually else 1,
        0 if row.tag_id is not None else 1,
        0 if row.confidence_score is not None else 1,
        0 if row.existing else 1,
        0 if row.rejected_at is None else 1,
        row.id,
    )


def _pick_survivor(rows: list[Tag]) -> Tag:
    """同一 `(image_id, model_id, normalized_tag)` の行集合から代表行を選ぶ。"""
    return sorted(rows, key=_survivor_sort_key)[0]


def build_repair_plan(session: Session) -> RepairPlan:
    """DB の全 Tag 行を走査して修復計画を構築する。

    Args:
        session: 対象 DB の SQLAlchemy セッション。

    Returns:
        算出された RepairPlan。
    """
    rows = list(session.execute(select(Tag)).scalars())
    plan = RepairPlan(total_count=len(rows))

    # (image_id, model_id) ごとにグループ化し、グループ内で normalized tag の衝突を解決する。
    groups: dict[tuple[int | None, int | None], list[Tag]] = {}
    for row in rows:
        groups.setdefault((row.image_id, row.model_id), []).append(row)

    for (image_id, model_id), group_rows in groups.items():
        by_normalized: dict[str, list[Tag]] = {}
        for row in group_rows:
            normalized = normalize_tag_value(row.tag)
            if not normalized:
                plan.empty_deletions.append(
                    TagDeletion(
                        tag_row_id=row.id,
                        image_id=image_id,
                        model_id=model_id,
                        old_tag=row.tag,
                        new_tag="",
                        survivor_row_id=None,
                    )
                )
                logger.debug(f"空整形で削除予定: id={row.id}, tag='{row.tag}'")
                continue
            by_normalized.setdefault(normalized, []).append(row)

        for normalized, dup_rows in by_normalized.items():
            survivor = _pick_survivor(dup_rows)
            for row in dup_rows:
                if row.id == survivor.id:
                    if row.tag != normalized:
                        plan.updates.append(
                            TagUpdate(
                                tag_row_id=row.id,
                                image_id=image_id,
                                model_id=model_id,
                                old_tag=row.tag,
                                new_tag=normalized,
                            )
                        )
                        logger.debug(f"整形更新予定: id={row.id}, '{row.tag}' -> '{normalized}'")
                    else:
                        plan.unchanged_count += 1
                else:
                    plan.duplicate_deletions.append(
                        TagDeletion(
                            tag_row_id=row.id,
                            image_id=image_id,
                            model_id=model_id,
                            old_tag=row.tag,
                            new_tag=normalized,
                            survivor_row_id=survivor.id,
                        )
                    )
                    logger.debug(
                        f"重複マージで削除予定: id={row.id}, '{row.tag}' -> '{normalized}' "
                        f"(survivor id={survivor.id})"
                    )

    return plan


def apply_repair_plan(session: Session, plan: RepairPlan) -> None:
    """修復計画を DB に適用する (呼び出し側がトランザクション境界を管理する)。

    重複削除を先に実行してから代表行を更新することで、論理一意性
    `(image_id, model_id, tag)` の一時的な衝突を避ける。

    Args:
        session: 対象 DB の SQLAlchemy セッション。
        plan: 適用する RepairPlan。
    """
    delete_ids = [d.tag_row_id for d in plan.duplicate_deletions]
    delete_ids.extend(d.tag_row_id for d in plan.empty_deletions)

    for tag_row_id in delete_ids:
        row = session.get(Tag, tag_row_id)
        if row is not None:
            session.delete(row)

    # 削除を flush してから更新を反映する。
    session.flush()

    for update in plan.updates:
        row = session.get(Tag, update.tag_row_id)
        if row is not None:
            row.tag = update.new_tag


def _make_session_factory(db_path: Path) -> sessionmaker[Session]:
    """対象 DB へのセッションファクトリを生成する (Qt 非依存、migration を行わない)。

    Args:
        db_path: 対象 image database (.db) の絶対パス。

    Returns:
        対象 DB にバインドされた sessionmaker。
    """
    engine = create_engine(
        f"sqlite:///{db_path.resolve()}?check_same_thread=False",
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _resolve_db_path(db_path: Path | None) -> Path:
    """対象 DB パスを解決する。未指定時は設定のデフォルト DB を使う。

    Args:
        db_path: ユーザー指定の DB パス。None の場合は設定から解決する。

    Returns:
        解決された DB パス。

    Raises:
        FileNotFoundError: 解決した DB ファイルが存在しない場合。
    """
    if db_path is None:
        from lorairo.database.db_core import IMG_DB_PATH

        resolved = IMG_DB_PATH
        logger.info(f"--db-path 未指定のため設定のデフォルト DB を使用: {resolved}")
    else:
        resolved = db_path

    resolved = resolved.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"対象 DB が見つかりません: {resolved}")
    return resolved


def _backup_database(db_path: Path) -> Path:
    """実書き込み前に DB ファイルをコピーしてバックアップする。

    Args:
        db_path: バックアップ対象の DB パス。

    Returns:
        作成したバックアップファイルのパス。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{timestamp}")
    shutil.copy2(db_path, backup_path)
    logger.info(f"バックアップを作成しました: {backup_path}")
    return backup_path


def _log_plan_summary(plan: RepairPlan) -> None:
    """修復計画のサマリを INFO で出力する。"""
    logger.info(
        f"対象タグ行: {plan.total_count}件 / 整形更新: {len(plan.updates)}件, "
        f"重複マージ削除: {len(plan.duplicate_deletions)}件, "
        f"空整形削除: {len(plan.empty_deletions)}件, 変更なし: {plan.unchanged_count}件"
    )


def _echo_diff_samples(plan: RepairPlan) -> None:
    """dry-run 時に diff のサンプルを標準出力へ表示する。"""
    shown = 0
    for update in plan.updates:
        if shown >= _DIFF_SAMPLE_LIMIT:
            break
        typer.echo(f"[update] id={update.tag_row_id} '{update.old_tag}' -> '{update.new_tag}'")
        shown += 1
    for deletion in plan.duplicate_deletions:
        if shown >= _DIFF_SAMPLE_LIMIT:
            break
        typer.echo(
            f"[merge-delete] id={deletion.tag_row_id} '{deletion.old_tag}' "
            f"-> '{deletion.new_tag}' (survivor id={deletion.survivor_row_id})"
        )
        shown += 1
    for deletion in plan.empty_deletions:
        if shown >= _DIFF_SAMPLE_LIMIT:
            break
        typer.echo(f"[empty-delete] id={deletion.tag_row_id} '{deletion.old_tag}' -> (empty)")
        shown += 1


def repair_database(db_path: Path, apply: bool, backup: bool = True) -> RepairPlan:
    """対象 DB のタグ整形を実行する (またはプレビューする)。

    Args:
        db_path: 対象 image database (.db) の絶対パス。
        apply: True で実書き込み、False で dry-run。
        backup: apply 時に書き込み前バックアップを取得するか。

    Returns:
        算出 (および適用) された RepairPlan。
    """
    session_factory = _make_session_factory(db_path)

    with session_factory() as session:
        plan = build_repair_plan(session)
        _log_plan_summary(plan)

        if not apply:
            logger.info("dry-run のため DB への書き込みは行いません (--apply で実書き込み)。")
            return plan

        if not plan.has_changes:
            logger.info("適用すべき変更がありません。")
            return plan

        if backup:
            _backup_database(db_path)

        apply_repair_plan(session, plan)
        session.commit()
        logger.info("タグ整形の書き込みが完了しました。")

    return plan


@app.command()
def repair(
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="対象 image database (.db) のパス。省略時は設定のデフォルト DB を使用。",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="実際に DB へ書き込む。指定しない場合は dry-run (プレビューのみ)。",
    ),
    backup: bool = typer.Option(
        True,
        "--backup/--no-backup",
        help="--apply 時に書き込み前バックアップを取得する (デフォルト: 取得する)。",
    ),
) -> None:
    """既存 DB の `tags.tag` を `clean_format` で一括整形する (Issue #769)。

    Args:
        db_path: 対象 DB パス。省略時は設定のデフォルト DB。
        apply: True で実書き込み、False (デフォルト) で dry-run。
        backup: --apply 時に書き込み前バックアップを取得するか。
    """
    resolved = _resolve_db_path(db_path)
    logger.info(f"タグ整形修復を開始します: db={resolved}, apply={apply}")

    plan = repair_database(resolved, apply=apply, backup=backup)

    if not apply:
        _echo_diff_samples(plan)


if __name__ == "__main__":
    app()
