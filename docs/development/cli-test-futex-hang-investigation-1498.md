# CLI テスト (`test_images_register_unsupported_file_format`) futex 待ち無期限停止の原因調査 (#1498)

## 1. 事象の概要

- **発生日時**: 2026-11-08 06:13 頃
- **観測された状態**: `tests/unit/cli/test_commands_images.py::test_images_register_unsupported_file_format` 付近で、一時プロジェクト DB (`image_database.db`) を `-wal` / `-shm` 付きで開いたまま、プロセスが `futex` 待ちで 52 分間無期限停止した。
- **再現性**:
  - `pytest tests/unit/cli/test_commands_images.py -k register` (12 件) を同一プロセスで 20 回反復（計 240 件）、および `tests/unit` 全体を CI 相当で反復実行した範囲では単独再現しなかった。

## 2. 原因メカニズムの分析

`#1492` / PR `#1496` / `#1497` / `#1498` の横断調査により、以下の 2 つのメカニズムが複合して発生する構造を特定した。

### メカニズム A: `ServiceContainer` における SQLAlchemy `Engine` 未破棄と循環参照 GC ファイナライザ競合

1. **サポート外ファイルでも WAL/SHM 付き Engine が 2 回生成される**:
   - `test_images_register_unsupported_file_format` は `test.txt` を渡して失敗終了するテストだが、ファイル形式判定の前に以下の 2 箇所で `set_active_project("test-project")` が呼ばれる:
     1. `lorairo.cli.commands.images:register()` (`get_service_container().set_active_project(project)`)
     2. `lorairo.public_api.images:register_images()` (`container.set_active_project(project_name)`)
   - 各 `set_active_project()` は `create_project_session_factory(db_path)` 経由で SQLAlchemy `Engine` (`QueuePool`) を生成し、`_ensure_wal_journal_mode()` により `-wal` / `-shm` を開いた接続をプールに保持する。
2. **Engine の参照サイクルと未破棄リーク**:
   - `db_core.create_db_engine()` 内の `@event.listens_for(engine, "connect")` リスナー (`configure_sqlite_listener`) がクロージャとして `engine` 自身を捕捉していたため、`engine -> dispatch -> configure_sqlite_listener -> engine` の循環参照が形成されていた。
   - `set_active_project()` の再呼び出しや `ServiceContainer.reset_container()` / `reset_for_testing()` は `self._image_repository = None` で参照を上書きするだけで `engine.dispose()` を呼んでいなかった。
   - さらに `tests/unit/cli/` には各テスト終了時に `ServiceContainer` シングルトンをリセットする teardown fixture が存在しなかった。
3. **モジュール終端での一括 GC 回収**:
   - `test_images_register_unsupported_file_format` は `tests/unit/cli/test_commands_images.py` の**末尾のテスト**であり、その直後に `tests/conftest.py` の module スコープ fixture `_collect_qt_wrappers_on_main_thread` が `gc.collect()` を実行する。
   - この時点で、モジュール内の全テストがリークした未 `dispose` の `Engine` / `QueuePool` / `sqlite3.Connection`（`-wal` / `-shm` を保持）が一斉に GC ファイナライザで回収され、`tmp_path` クリーンアップやロック取得と競合する。

### メカニズム B: 同一 `tests/unit` セッション内の残留 Qt Worker スレッドとの ABBA デッドロック (`#1492` / `#1496` / `#1497`)

- `tests/unit` 全体を実行するセッションでは、先行する GUI ユニットテストが起動した `QThread` ワーカーが残留する場合がある。
- Python 製 `QObject` サブクラスである Worker が worker スレッド上で破棄 (`~QObject` -> `SbkDeallocWrapper` -> `PyGILState_Ensure`) されると、**Qt 内部の `signalSlotLock` を保持したまま Python GIL を待つ**一方、メインスレッド（または GC 実行中スレッド）が **GIL を保持したまま Qt ロックや C レベル mutex (futex) を待つ** ABBA デッドロックが発生する。
- この状態に入ると `pytest-timeout` (signal / thread 方式) でも割り込めず、プロセスは futex 待ちのまま無期限停止する。

## 3. 対策と再発防止・診断強化

1. **`pyproject.toml` に `faulthandler_timeout = 60` を設定**:
   - `[tool.pytest.ini_options]` に `faulthandler_timeout = 60` を常時有効化。万一 futex 待ち等で 60 秒以上停止した場合、CI のジョブタイムアウト等で強制終了される前に C レベル / Python レベルの全スレッドスタックを自動ダンプする。
   - ローカル・CI での再現調査時は必要に応じて `sudo py-spy dump --native --pid <pid>` を併用する。
2. **`ServiceContainer` での明示的 `engine.dispose()`**:
   - `ServiceContainer._dispose_active_engines()` を実装し、`reset_container()` (`reset_for_testing()`)、`set_active_project()`、`image_repository` deleter、および `service_container_scope()` 終了時に、保持中の SQLAlchemy `Engine` を重複なく明示破棄 (`engine.dispose()`) する。
3. **`db_core.create_db_engine()` の循環参照解消**:
   - `configure_sqlite_listener` クロージャ内で `engine` インスタンスを参照しないよう `is_sqlite` を事前評価し、`Engine` の循環参照を除去した。
4. **全テスト共通 teardown (`reset_service_container_singleton`)**:
   - `tests/conftest.py` に `autouse=True` の `reset_service_container_singleton` フィクスチャを追加し、CLI テストを含む全テストの前後で `ServiceContainer.reset_for_testing()` を実行して一時 DB の WAL/SHM ロックをテスト終了時点で確実に解放する。
