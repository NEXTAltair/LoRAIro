"""旧 ~/.lorairo/projects/ を lorairo_data/ に移行するスクリプト。

このスクリプトはファイルコピーのみを担当します。
DB バックフィル (images.project_id) は以下で実施:
  uv run alembic upgrade head
"""

import fcntl
import shutil
import sys
from io import TextIOWrapper
from pathlib import Path

import typer
from loguru import logger

from lorairo.utils.config import get_config

app = typer.Typer(help="Migrate legacy ~/.lorairo/projects/ to lorairo_data/")


def _resolve_target_dir(target_dir: Path | None) -> Path:
    """ターゲットディレクトリを解決する。

    Args:
        target_dir: ユーザー指定のターゲットディレクトリ。None の場合は設定から取得。

    Returns:
        解決されたターゲットディレクトリのパス。
    """
    if target_dir is not None:
        return target_dir

    config = get_config()
    base_dir: str = config.get("directories", {}).get("database_base_dir", "lorairo_data")
    # スクリプトはプロジェクトルートから実行されることを想定
    project_root = Path(__file__).parent.parent
    return project_root / base_dir


def _acquire_lock(lock_path: Path) -> TextIOWrapper:
    """排他ロックファイルを取得する。

    Args:
        lock_path: ロックファイルのパス。

    Returns:
        オープン済みのロックファイルオブジェクト。

    Raises:
        SystemExit: ロックファイル作成失敗またはロック取得失敗時に exit_code=1 で終了。
    """
    try:
        lock_file = open(lock_path, "w")  # TextIOWrapper が必要なため with 構文は使用しない
    except OSError as e:
        logger.error(f"ロックファイルの作成に失敗しました: {lock_path} — {e}", exc_info=True)
        sys.exit(1)

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("別のプロセスが移行中です。ロックの取得に失敗しました。")
        lock_file.close()
        sys.exit(1)

    return lock_file


def _release_lock(lock_file: TextIOWrapper, lock_path: Path) -> None:
    """排他ロックを解放してロックファイルを削除する。

    Args:
        lock_file: オープン済みのロックファイルオブジェクト。
        lock_path: ロックファイルのパス。
    """
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _copy_one(src: Path, dst: Path) -> tuple[int, int, int]:
    """単一ディレクトリをコピーする。

    Args:
        src: コピー元ディレクトリ。
        dst: コピー先ディレクトリ。

    Returns:
        (success, skip, error) のタプル。各値は 0 または 1。
    """
    if dst.exists():
        logger.warning(f"移行先に既にディレクトリが存在するためスキップ: {dst}")
        return 0, 1, 0

    logger.debug(f"コピー開始: {src} → {dst}")
    try:
        shutil.copytree(src, dst)
        logger.debug(f"コピー完了: {dst}")
    except (OSError, shutil.Error) as e:
        logger.error(f"コピーに失敗しました: {src} → {dst} — {e}", exc_info=True)
        shutil.rmtree(dst, ignore_errors=True)
        return 0, 0, 1

    return 1, 0, 0


def _run_migration(
    candidates: list[Path],
    source_root: Path,
    resolved_target: Path,
    backup: bool,
) -> None:
    """排他ロックを取得してディレクトリ群を移行する。

    Args:
        candidates: 移行対象のソースディレクトリ一覧。
        source_root: 移行元のルートディレクトリ（~/.lorairo/projects）。
        resolved_target: 移行先のベースディレクトリ。
        backup: True の場合、全コピー完了後にソースルートを .bak にリネームする。
    """
    lock_path = resolved_target / ".migrate.lock"
    lock_file = _acquire_lock(lock_path)

    success_count = 0
    skip_count = 0
    error_count = 0

    try:
        for src in candidates:
            dst = resolved_target / src.name
            s, sk, e = _copy_one(src, dst)
            success_count += s
            skip_count += sk
            error_count += e
    finally:
        _release_lock(lock_file, lock_path)

    logger.info(f"移行完了: 成功={success_count}, スキップ={skip_count}, エラー={error_count}")

    if backup and success_count > 0 and error_count == 0:
        bak_path = source_root.parent / (source_root.name + ".bak")
        try:
            source_root.rename(bak_path)
            logger.info(f"バックアップ完了: {source_root} → {bak_path}")
        except OSError as e:
            logger.warning(f"バックアップのリネームに失敗しました: {source_root} → {bak_path}: {e}")


@app.command()
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, no changes"),
    backup: bool = typer.Option(False, "--backup", "-b", help="Rename source to .bak after copy"),
    target_dir: Path | None = typer.Option(None, "--target-dir", help="Migration destination directory"),
    source_dir: Path | None = typer.Option(None, "--source-dir", help="Migration source directory"),
) -> None:
    """旧 ~/.lorairo/projects/ を lorairo_data/ に移行する。

    このコマンドはファイルコピーのみを担当します。
    DB バックフィル (images.project_id) は `uv run alembic upgrade head` で実施してください。

    Args:
        dry_run: True の場合、実際のコピーは行わずプレビューのみ表示する。
        backup: True の場合、コピー後に旧ディレクトリを .bak にリネームする。
        target_dir: 移行先ディレクトリ。省略時は設定ファイルの database_base_dir を使用。
        source_dir: 移行元ディレクトリ。省略時は ~/.lorairo/projects/ を使用。
    """
    resolved_source = source_dir if source_dir is not None else Path.home() / ".lorairo" / "projects"
    resolved_target = _resolve_target_dir(target_dir)

    # ソースディレクトリ存在確認
    if not resolved_source.exists():
        logger.info(f"移行元ディレクトリが存在しないためスキップします: {resolved_source}")
        return

    # ターゲットディレクトリ確認・作成 (dry-run では作成しない)
    if not dry_run:
        resolved_target.mkdir(parents=True, exist_ok=True)
        logger.debug(f"移行先ディレクトリを確認しました: {resolved_target}")

    # 移行対象ディレクトリの列挙
    candidates = [p for p in resolved_source.iterdir() if p.is_dir()]
    logger.info(f"移行対象: {len(candidates)}件")

    if not candidates:
        logger.info("移行対象のディレクトリが見つかりませんでした。")
        return

    if dry_run:
        for src in candidates:
            dst = resolved_target / src.name
            typer.echo(f"[dry-run] {src} → {dst}")
            logger.debug(f"移行予定: {src} → {dst}")
        logger.info(f"dry-run 完了: 移行予定 {len(candidates)} 件")
        return

    _run_migration(candidates, resolved_source, resolved_target, backup)


if __name__ == "__main__":
    app()
