# Kohya-ss データセットの取り込みと書き出し(コア)実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kohya-ss 学習用データセットを、版・フォルダ・学習テキストとして取り込み、取り込み時と同じ形(フォルダ、`.txt`、sd-scripts 用 TOML)で書き出せるコア機能を Qt 非依存で実装する。

**Architecture:** 新規 6 テーブル(`datasets`、`dataset_versions`、`dataset_folders`、`dataset_folder_images`、`dataset_learning_texts`、`training_configs`)と `DatasetRepository` を追加する。取り込み、書き出し、設定の正規化は Qt 非依存のサービスとして実装し、CLI から実行する。画像直下の `Tag` テーブルには一切書き込まない。GUI の取り込みダイアログは、本コアの API が固まってから別計画(Plan B)で実装する。

**Tech Stack:** SQLAlchemy 2、Alembic(SQLite)、Typer(CLI)、`toml`(既存依存)、pytest

**Spec:** `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`(以降「設計書」と呼ぶ)。調査の数値根拠は Issue #1404 に記載されている。

## 全体制約

- 作業は `.agents/worktree/` 配下のワークツリー(`git worktree add .agents/worktree/kohya-ds -b feat/kohya-dataset-core origin/main`)で行う。`uv run` は常にプロジェクトルートから実行する(CLAUDE.md)。
- Ruff の最大行長は 108 文字とし、全関数に型ヒントを付ける。`# type: ignore` および `# noqa` は禁止し、`Any` と広い `except Exception` を避けて具体的な例外のみを捕捉する。
- docstring は Google スタイル、実装コメントは日本語とする。ログには `from lorairo.utils.log import logger`(Loguru)を用い、INFO はバッチ要約のみ、個別項目は DEBUG とする。
- サービスは Qt 非依存(`src/lorairo/services/` で Qt をインポートしない)とする。リポジトリは `BaseRepository` を継承し、`session_factory` を受け取る(ADR 0035)。
- Alembic の現在の head は `d4e5f6a7b8c9` であり、新規マイグレーションの `down_revision` に指定する。SQLite では `batch_alter_table`、新規テーブル作成では `op.create_table` を使う。`Base.metadata.create_all()`(テスト用)と Alembic の両方で同一テーブルが生成されることを保証する。
- 用語はデータセット側で「学習テキスト」「要素」「トリガーワード」を用い、画像直下の「タグ」(`Tag`)と混同しない(設計書 §0)。
- 取り込み時に `TagCleaner.clean_format` を使用しない。要素分割はカンマ分割と前後空白の除去のみを行う(設計書 §4)。
- 秘密の値(`*_api_key`、`*_token` で終わるキー)は保存も書き出しもしない。`raw_content` に残る値も空文字へ置換してから保存する(設計書 §9.5)。
- 取り込む画像は各フォルダの**直下のみ**とする。sd-scripts の既定値は `.caption` であるため、書き出し時は `.txt` または `.caption` の `caption_extension` を必ず明示する。
- 版の `raw_text` は取り込み後に書き換えない。リポジトリに `raw_text` の更新 API を設けない。
- テストは `tests/unit` と `tests/integration` に配置し、カバレッジ 75% 以上を維持する。コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` を付与する。
- 実データ(`H:\`)は本コンテナから参照できないため、テストでは `tmp_path` に実データの構造を再現したフィクスチャを用いる。

## レビューの重点項目

1. 同じ画像が 2 つのフォルダに存在し、別々の `.txt` を持つ場合、学習テキストは別々のまま保持され、`Tag` テーブルは 0 行のままであること(Task 8)。
2. 作業用フォルダ(`sample001`、`終了`、`*__Processed`)およびフォルダ直下より深い階層の画像は取り込まれないこと(Task 4、8)。
3. 設定 JSON の空文字キーが出力されず、`wandb_api_key` の値が `raw_content` にも `normalized_json` にも残らないこと(Task 6)。
4. `(tag:1.2)`、大文字、アンダースコア、CRLF、複数行を含む `.txt` が、未編集の書き出しで文字列として完全一致すること(Task 9)。
5. `.txt` が無い画像は所属のみ記録され、書き出し時に `.txt` を生成しないこと。また、画像の無い `.txt` は無視されること(Task 4、9)。
6. 同じ版への二重取り込みや同名のフォルダ・版の作成で `DatasetConflictError` が送出され、中途半端な行が残らないこと(Task 3、8)。

---

### Task 1: 学習テキストの要素分割と連結

**Files:**
- Create: `src/lorairo/services/learning_text.py`
- Test: `tests/unit/services/test_learning_text.py`

**Interfaces:**
- 提供(Produces): `split_elements(raw_text: str) -> list[str]`、`join_elements(elements: list[str]) -> str`

- [ ] **Step 1: 失敗するテストを書く**
  - `test_split_elements_keeps_case_underscore_and_parentheses`: `"Kariginu, long_sleeves, (tag:1.2), \\(x\\)"` が `["Kariginu", "long_sleeves", "(tag:1.2)", "\\(x\\)"]` になることを検証する。
  - `test_split_elements_drops_empty_items`: `"a,, b ,\n"` が `["a", "b"]` になることを検証する。
  - `test_split_elements_multiline_is_joined_by_comma_only`: 改行を要素の区切りとせず、改行を含む要素を 1 つとして残す(`"a\nb, c"` が `["a\nb", "c"]` になる)。
  - `test_join_elements_uses_comma_space`: `["a", "b"]` が `"a, b"` になることを検証する。
- [ ] **Step 2: 実行して失敗を確認する**(`uv run pytest tests/unit/services/test_learning_text.py -v` がインポートエラーで失敗する)
- [ ] **Step 3: `split_elements` と `join_elements` を実装する**(`str.split(",")` と `strip()` のみを行い、正規化しない)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: 学習テキストの要素分割と連結を追加する`

---

### Task 2: スキーマと Alembic マイグレーション

**Files:**
- Modify: `src/lorairo/database/schema.py`(クラスを `Project` の後ろに追加する)
- Create: `src/lorairo/database/migrations/versions/<新rev>_add_dataset_tables.py`(`down_revision = "d4e5f6a7b8c9"`)
- Test: `tests/unit/database/test_dataset_schema.py`

**Interfaces:**
- 提供(Produces、すべて `Base` を継承し `Mapped[...]` スタイルで記述。既存の `Project` を参照):
  - `Dataset`: `id`、`name`(UNIQUE、index)、`description: str | None`、`created_at`
  - `DatasetVersion`: `id`、`dataset_id`(FK `datasets.id` CASCADE)、`parent_version_id`(自己 FK、SET NULL、nullable)、`name`、`created_at`。UNIQUE(`dataset_id`, `name`)
  - `DatasetFolder`: `id`、`version_id`(FK CASCADE)、`dir_name`(例: `10_kariginu`)、`name`(例: `kariginu`)、`num_repeats: int`、`trigger_word: str | None`、`position: int`。UNIQUE(`version_id`, `dir_name`)
  - `DatasetFolderImage`: `id`、`folder_id`(FK CASCADE)、`image_id`(FK `images.id` CASCADE)、`file_stem: str`。UNIQUE(`folder_id`, `file_stem`)。`image_id` にインデックスを張る。
  - `DatasetLearningText`: `id`、`folder_image_id`(FK CASCADE)、`extension: str`(`.txt` または `.caption`)、`raw_text: str`(Text)、`elements_json: str`(Text、JSON 文字列リスト)、`is_edited: bool`(デフォルト `False`)。UNIQUE(`folder_image_id`, `extension`)
  - `TrainingConfig`: `id`、`dataset_id`(FK CASCADE)、`version_id`(FK SET NULL、nullable)、`source_kind: str`(`kohya_gui_json`、`sd_scripts_toml`、`bat`、`safetensors_header`)、`source_file_name: str`、`raw_content: str`(Text)、`normalized_json: str`(Text)、`unmapped_json: str`(Text)、`target_script: str | None`、`output_name: str | None`、`base_model: str | None`、`resolution: str | None`、`network_dim: int | None`、`network_alpha: float | None`、`learning_rate: float | None`、`created_at`

- [ ] **Step 1: 失敗するテストを書く**
  - `test_create_all_creates_dataset_tables`: `Base.metadata.create_all(engine)` 実行後、`inspect(engine).get_table_names()` に 6 テーブルが含まれることを検証する。
  - `test_alembic_upgrade_head_creates_dataset_tables`: 既存のマイグレーションテスト(`grep -rn "command.upgrade" tests`)と同様に一時 DB へ `upgrade head` を実行し、同じ 6 テーブルが作成されることを検証する。
  - `test_alembic_has_single_head`: `ScriptDirectory.from_config(...).get_heads()` の要素数が 1 であることを検証する。
  - `test_deleting_version_cascades_to_folders_texts`: SQLite の `PRAGMA foreign_keys=ON` を有効化した既存接続設定を使い、ORM で作成した version を削除した際に folder、folder_image、learning_text が連鎖削除されることを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: スキーマクラスを `schema.py` に、マイグレーションを新規ファイルに実装する**(マイグレーションの docstring に Issue #1404 と設計書へのパスを記載する)
- [ ] **Step 4: テスト通過と `uv run mypy -p lorairo` の成功を確認する**
- [ ] **Step 5: コミットする** `feat: データセット関連テーブルと migration を追加する`

---

### Task 3: `DatasetRepository`

**Files:**
- Create: `src/lorairo/database/repository/dataset.py`
- Test: `tests/unit/database/repository/test_dataset_repository.py`

**Interfaces:**
- 依存(Consumes): Task 2 のモデル、`BaseRepository`
- 提供(Produces):
  - `class DatasetConflictError(ValueError)`
  - `@dataclass(frozen=True) class FolderSpec: dir_name: str; name: str; num_repeats: int; trigger_word: str | None; position: int`
  - `@dataclass(frozen=True) class LearningTextSpec: extension: str; raw_text: str; elements: list[str]`
  - `@dataclass(frozen=True) class FolderImageSpec: image_id: int; file_stem: str; texts: list[LearningTextSpec]`
  - `DatasetRepository.ensure_dataset(name: str, description: str | None = None) -> int`
  - `DatasetRepository.create_version(dataset_id: int, name: str, parent_version_id: int | None = None) -> int`(同名が存在する場合は `DatasetConflictError` を送出)
  - `DatasetRepository.add_folder(version_id: int, spec: FolderSpec, images: list[FolderImageSpec]) -> int`(1 トランザクションで実行し、途中失敗時は何も残さない)
  - `DatasetRepository.get_version_snapshot(version_id: int) -> VersionSnapshot`: `VersionSnapshot` は `dataset_name`、`version_name`、`parent_version_id`、`folders: list[FolderSnapshot]` を持つ frozen dataclass とする。`FolderSnapshot` は `FolderSpec` の項目に `id` と `images: list[FolderImageSnapshot]` を加えたもの、画像は `image_id`、`file_stem`、`texts: list[LearningTextSnapshot]`(`id`、`extension`、`raw_text`、`elements`、`is_edited`)を持つ。
  - `DatasetRepository.update_learning_text_elements(text_id: int, elements: list[str]) -> None`(`elements_json` を更新し `is_edited=True` にする。`raw_text` は変更しない)
  - `DatasetRepository.set_folder_trigger_word(folder_id: int, trigger_word: str | None) -> None`
  - `DatasetRepository.add_training_config(dataset_id: int, version_id: int | None, spec: TrainingConfigSpec) -> int`、`list_training_configs(dataset_id: int) -> list[TrainingConfigSnapshot]`、`get_training_config(config_id: int) -> TrainingConfigSnapshot`。`TrainingConfigSpec` と `TrainingConfigSnapshot` は Task 2 の `TrainingConfig` の列と同名のフィールドを持つ frozen dataclass とする。

- [ ] **Step 1: 失敗するテストを書く**(`test_engine_with_schema` および `db_session_factory` フィクスチャを使い、既存ヘルパーで `Image` 行を 1 件作成する)
  - `test_same_image_in_two_folders_keeps_separate_texts`: 同じ `image_id` を 2 フォルダへ異なる `raw_text` で登録し、スナップショット上で別々の `raw_text` が保持されることを検証する。
  - `test_create_version_with_same_name_raises_conflict`: 同名版の作成で `DatasetConflictError` が送出されることを検証する。
  - `test_add_folder_is_atomic`: 2 枚目の画像に存在しない `image_id` を指定した場合、フォルダ行も 1 枚目の行も残らないことを検証する(`IntegrityError` を `DatasetConflictError` へ変換するかは実装判断とする)。
  - `test_update_learning_text_elements_keeps_raw_text`: 更新後も `raw_text` が元のままであり、`elements` が更新され `is_edited` が `True` になることを検証する。
  - `test_version_parent_is_recorded`: 親版 ID が記録されることを検証する。
  - `test_training_config_roundtrip`: 追加と取得で全フィールドが一致することを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**(`elements_json` の保存には `json.dumps(..., ensure_ascii=False)` を使う)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: DatasetRepository を追加する`

---

### Task 4: Kohya ディレクトリのスキャナ

**Files:**
- Create: `src/lorairo/services/kohya_scanner.py`
- Test: `tests/unit/services/test_kohya_scanner.py`

**Interfaces:**
- 依存(Consumes): Task 1 の `split_elements`、`lorairo.utils.tools.decode_text_with_fallback`
- 提供(Produces):
  - `DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...]` = `("sample*", "終了", "*__Processed", "reg", "log", "logs", "wandb")`(フォルダ名に対する `fnmatch` パターン)
  - `@dataclass(frozen=True) class ScannedImage: path: Path; file_stem: str; texts: list[ScannedText]`、および `ScannedText: extension: str; raw_text: str; elements: list[str]`
  - `@dataclass(frozen=True) class ScannedFolder: dir_path: Path; dir_name: str; name: str; num_repeats: int; images: list[ScannedImage]; trigger_candidate: str | None; trigger_match_rate: float`
  - `scan_kohya_directory(root: Path, exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS) -> list[ScannedFolder]`
  - `parse_folder_name(dir_name: str) -> tuple[int, str] | None`(例: `10_kariginu` を `(10, "kariginu")` に分解する。`abe no seimei` のようなスペースを含む名前も許容し、接頭辞が数字と `_` でなければ `None` を返す)

- [ ] **Step 1: 失敗するテストを書く**(`tmp_path` に PIL で 8x8 の画像を生成する小ヘルパーを使用する)
  - `test_parse_folder_name_extracts_repeats_and_name`: `"10_abe no seimei"` が `(10, "abe no seimei")` になり、`"sample001"` が `None` になることを検証する。
  - `test_scan_reads_only_direct_children_of_folders`: `root/10_a/x.png` は取り込み、`root/10_a/sub/y.png` は取り込まないことを検証する。
  - `test_scan_skips_excluded_and_non_repeat_folders`: `sample001`、`終了`、`10_a__Processed`、`log` が結果に含まれないことを検証する。
  - `test_scan_reads_txt_and_caption_raw_text`: `x.txt` の `raw_text` が元のまま保持され(CRLF を含む文字列で検証)、`.caption` が別の `ScannedText` として読み込まれることを検証する。
  - `test_scan_image_without_text_has_empty_texts`: `.txt` の無い画像では `texts == []` となることを検証する。
  - `test_scan_ignores_text_without_image`: 画像の無いテキストファイルが無視されることを検証する。
  - `test_trigger_candidate_uses_most_common_first_element`: 5 枚中 5 枚が `kariginu` で始まる場合は `("kariginu", 1.0)` となる。5 枚中 1 枚のみ共通なら `trigger_match_rate` は 0.2 となり、候補は `None` とする(閾値は定数 `TRIGGER_CANDIDATE_MIN_RATE = 0.5` 以上)。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**(画像拡張子は既存の定数を `grep -rn "\.webp" src/lorairo | head` で探して流用する)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: Kohya ディレクトリのスキャナを追加する`

---

### Task 5: sd-scripts の引数表

**Files:**
- Create: `scripts/gen_sd_scripts_arg_table.py`(開発用スクリプト。`src` からは参照しない)
- Create: `src/lorairo/services/sd_scripts_arg_table.py`(生成物。先頭コメントに sd-scripts のコミット `cb70b96` と生成日を記載する)
- Test: `tests/unit/services/test_sd_scripts_arg_table.py`

**Interfaces:**
- 提供(Produces): `SD_SCRIPTS_ARG_TYPES: dict[str, str]`(引数名から `"int" | "float" | "str" | "bool"` へのマップ。`type=` が無く `action="store_true"` または `"store_false"` なら `"bool"`、いずれも無ければ `"str"` とする)

- [ ] **Step 1: 失敗するテストを書く**
  - `test_table_contains_known_args`: `learning_rate` が `"float"`、`network_dim` が `"int"`、`gradient_checkpointing` が `"bool"`、`optimizer_type` と `log_with` が `"str"` であることを検証する。
  - `test_table_excludes_launcher_and_gui_only_keys`: `num_cpu_threads_per_process`、`LoRA_type`、`sdxl` が含まれないことを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 生成スクリプトを実装して引数表を生成する**(空ディレクトリへ `git fetch --depth 1 origin cb70b96` で sd-scripts を取得し、`library/*.py`、`train_network.py`、`sdxl_train_network.py` を `ast` で解析する。`add_argument` 呼び出しの最初の文字列定数 `--xxx` と `type=` / `action=` を収集し、実行せずに読み取りのみで生成する。結果を `sd_scripts_arg_table.py` へ書き出してコミット対象にする)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: sd-scripts の引数表を追加する`

---

### Task 6: Kohya_ss 設定 JSON の正規化

**Files:**
- Create: `src/lorairo/services/kohya_config_normalizer.py`
- Test: `tests/unit/services/test_kohya_config_normalizer.py`

**Interfaces:**
- 依存(Consumes): Task 5 の `SD_SCRIPTS_ARG_TYPES`
- 提供(Produces):
  - `@dataclass(frozen=True) class NormalizedConfig: raw_content: str; normalized: dict[str, str | int | float | bool | list[str]]; unmapped: dict[str, str | int | float | bool | list[str] | None]; target_script: str | None; output_name: str | None`
  - `normalize_kohya_gui_config(raw_text: str) -> NormalizedConfig`(`json.JSONDecodeError` はそのまま伝播させる)
  - `mask_secrets(config: dict[str, object]) -> dict[str, object]`(`*_api_key` または `*_token` で終わるキーの値を `""` に置換した新しい辞書を返す)

変換規則は設計書 §9.5 および Issue #1404 のコメントを根拠とする。出典は Kohya_ss(コミット `45088f0`)の `kohya_gui/lora_gui.py` と `common_gui.py` であり、判断に迷った場合は同版のソースを参照する。

| 入力 | 出力 |
|---|---|
| `""` または `None` の値 | 取り除く(`unmapped` にも入れない) |
| 秘密キー | `mask_secrets` で `raw_content` の値を空文字にし、`normalized` および `unmapped` へ出さない |
| 起動ツール引数(`extra_accelerate_launch_args`、`gpu_ids`、`main_process_port`、`multi_gpu`、`num_cpu_threads_per_process`、`num_machines`、`num_processes`) | 取り除く |
| `optimizer`、`sdxl_cache_text_encoder_outputs`、`sdxl_no_half_vae`、`lora_network_weights`、`max_resolution` | それぞれ `optimizer_type`、`cache_text_encoder_outputs`、`no_half_vae`、`network_weights`、`resolution` に改名する |
| `use_wandb` が真 | `log_with = "wandb"` とする。偽なら取り除く |
| `lr_warmup`(比率 %) | `common_gui.py:1185` の `resolve_lr_warmup_steps` と同じ規則で `lr_warmup_steps` を算出する。算出できない場合は `unmapped` に残す |
| `sdxl` が真 | `target_script = "sdxl_train_network.py"` とし、偽または未指定は `"train_network.py"` とする。`sdxl` キー自体は出力しない |
| `LoRA_type == "Standard"` | `network_module = "networks.lora"` とする |
| `LoRA_type` が `"LyCORIS/LoCon"` または `"LoCon"` | `network_module = "lycoris.kohya"` とし、`network_args` は `lora_gui.py:1841-1843` の LoCon 組み立てと同一キー・同一順序の `["k=v", ...]` とする |
| その他の `LoRA_type` | `LoRA_type` および関連する LyCORIS 系キーをすべて `unmapped` に残す |
| 上記以外で `SD_SCRIPTS_ARG_TYPES` にあるキー | そのまま出力し、値は引数表の型へ変換する(例: `"0.0001"` → `0.0001`、`"true"` → `True`) |
| 上記以外で引数表に無いキー | `unmapped` に残す |

- [ ] **Step 1: 失敗するテストを書く**(入力には辞書を `json.dumps` した文字列を使う)
  - `test_empty_string_keys_are_dropped`: `{"reg_data_dir": "", "dataset_config": ""}` が `normalized` にも `unmapped` にも出ないことを検証する。
  - `test_secret_value_is_masked_everywhere`: `{"wandb_api_key": "SECRET"}` に対し、`"SECRET"` が `raw_content`、`normalized`、`unmapped` の文字列表現のいずれにも含まれないことを検証する。
  - `test_renames_and_wandb_mapping`: `{"optimizer": "AdamW8bit", "use_wandb": true, "max_resolution": "1024,1024"}` が `normalized == {"optimizer_type": "AdamW8bit", "log_with": "wandb", "resolution": "1024,1024"}` になることを検証する。
  - `test_numeric_strings_are_coerced`: `{"learning_rate": "0.0001", "max_data_loader_n_workers": "0"}` がそれぞれ `0.0001`(float)と `0`(int)に変換されることを検証する。
  - `test_sdxl_flag_selects_script`: `{"sdxl": true}` で `target_script == "sdxl_train_network.py"` となり、`"sdxl"` が `normalized` に含まれないことを検証する。
  - `test_standard_lora_type_sets_network_module`: `Standard` 指定で `network_module` が設定されることを検証する。
  - `test_locon_packs_network_args`: `{"LoRA_type": "LyCORIS/LoCon", "conv_dim": 8, "conv_alpha": 1}` で `network_module == "lycoris.kohya"` となり、`network_args` に `"conv_dim=8"` と `"algo=locon"` が含まれることを検証する。
  - `test_other_lora_type_goes_to_unmapped`: `{"LoRA_type": "LyCORIS/LoHa"}` で `unmapped["LoRA_type"] == "LyCORIS/LoHa"` となり、`network_module` が `normalized` に含まれないことを検証する。
  - `test_output_name_is_extracted`: `output_name` が抽出されることを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: Kohya_ss 設定 json の正規化を追加する`

---

### Task 7: sd-scripts 用 TOML の書き出し関数

**Files:**
- Create: `src/lorairo/services/sd_scripts_toml.py`
- Test: `tests/unit/services/test_sd_scripts_toml.py`

**Interfaces:**
- 提供(Produces):
  - `@dataclass(frozen=True) class SubsetSpec: image_dir: Path; num_repeats: int; caption_extension: str`
  - `render_dataset_config(subsets: list[SubsetSpec]) -> str`: `[general]` の `caption_extension`、`[[datasets]]`、および `[[datasets.subsets]]`(`image_dir`、`num_repeats`、`caption_extension`)を出力する。`caption_extension` は必ず明示する。
  - `render_training_config(normalized: dict[str, str | int | float | bool | list[str]], path_overrides: dict[str, Path]) -> str`: フラットな TOML を `toml.dumps` で生成する。`path_overrides` のキー(`train_data_dir`、`output_dir`、`logging_dir` など)は文字列へ変換して上書きする。`reg_data_dir` は上書き指定がない限り出力しない。

- [ ] **Step 1: 失敗するテストを書く**
  - `test_dataset_config_has_explicit_caption_extension`: `toml.loads` の結果で `general.caption_extension` と各 subset の `caption_extension` が `".txt"` であることを検証する。
  - `test_dataset_config_subsets`: 2 つの `SubsetSpec` に対し、`datasets[0].subsets` が 2 件となり `num_repeats` と `image_dir` が一致することを検証する。
  - `test_training_config_is_flat_and_overrides_paths`: `normalized` の `train_data_dir = "/old"` を `path_overrides={"train_data_dir": Path("/new")}` で上書きした場合、出力の `train_data_dir == "/new"` となりセクション(`[...]`)が含まれないことを検証する。
  - `test_training_config_omits_reg_data_dir_unless_given`: 指定がない場合に `reg_data_dir` が省略されることを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**(検証として sd-scripts の `library/config_util.py` を確認し、`--dataset_config` 使用時に `resolution`、`batch_size`、`enable_bucket` が引数側から補われるかを確かめる。補われない場合は `render_dataset_config` にそれら 3 つの任意引数を追加して `[[datasets]]` へ出力し、確認結果を関数の docstring に 1 行で残す)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: sd-scripts 用 TOML の書き出し関数を追加する`

---

### Task 8: 取り込みサービス

**Files:**
- Create: `src/lorairo/services/dataset_import_service.py`
- Test: `tests/integration/services/test_dataset_import_service.py`

**Interfaces:**
- 依存(Consumes): Task 1、3、4、6、および `ImageDatabaseManager.register_original_image(image_path, fsm) -> tuple[int, dict[str, Any]] | None`(**`register_image_with_side_effects` は `Tag` テーブルへ書き込むため使用しない**)。
- 提供(Produces):
  - `@dataclass(frozen=True) class FolderImportPlan: dir_name: str; name: str; num_repeats: int; trigger_word: str | None; include: bool`
  - `@dataclass(frozen=True) class DatasetImportPlan: dataset_name: str; version_name: str; parent_version_id: int | None; folders: list[FolderImportPlan]; config_files: list[Path]`
  - `@dataclass(frozen=True) class DatasetImportResult: dataset_id: int; version_id: int; folder_count: int; image_count: int; skipped_images: int; training_config_ids: list[int]`
  - `class DatasetImportService`: `__init__(self, db_manager: ImageDatabaseManager, repository: DatasetRepository, fsm: FileSystemManager)`、`import_directory(self, root: Path, plan: DatasetImportPlan) -> DatasetImportResult`、`propose_plan(self, root: Path, dataset_name: str, version_name: str) -> DatasetImportPlan`(スキャン結果と `root` 直下の `*.json` の `output_name` から版名候補を生成するが、確定はしない)

- [ ] **Step 1: 失敗するテストを書く**(`tmp_path` に Kohya 形式のディレクトリを作成する。`10_a/` と `5_b/` に同じ画像ファイルを置いて別内容の `.txt` を配置し、`sample001/` に画像、`10_a/` に `.caption` のみの画像と `.txt` 無しの画像を置く)
  - `test_same_image_in_two_folders_keeps_separate_texts_and_no_tags`: 取り込み後、スナップショットの 2 フォルダが同じ `image_id` と異なる `raw_text` を持ち、`SELECT count(*) FROM tags` が 0 であることを検証する。
  - `test_excluded_folders_are_not_imported`: `sample001` の画像が `images` テーブルへ増えないことを検証する。
  - `test_image_without_text_is_member_without_text`: テキストの無い画像がテキストなしで所属記録されることを検証する。
  - `test_trigger_word_is_stored_only_from_plan`: `plan.folders[i].trigger_word` のみが保存され、スキャンの候補は自動保存されないことを検証する。
  - `test_duplicate_import_into_same_version_raises_conflict_and_leaves_no_rows`: 同一版への二重取り込みが `DatasetConflictError` となり、行が残らないことを検証する。
  - `test_config_json_is_stored_with_masked_secret`: `wandb_api_key` を含む設定 JSON を取り込んだ際、`training_configs.raw_content` に秘密の値が残らないことを検証する。
  - `test_propose_plan_uses_output_name_as_version_hint`: `output_name` が版名候補に反映されることを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**(1 フォルダごとに `add_folder` を 1 トランザクションで実行する。`register_original_image` が `None` を返した画像登録失敗は `skipped_images` に計上し、DEBUG ログへ記録する。`config_files` は `source_kind="kohya_gui_json"` として `normalize_kohya_gui_config` に通し、`TrainingConfigSpec` の `output_name`、`base_model`(`pretrained_model_name_or_path`)、`resolution`、`network_dim`、`network_alpha`、`learning_rate` は `normalized` から取り出す。存在しない場合は `None` とする)
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: データセットの取り込み service を追加する`

---

### Task 9: 書き出しサービス

**Files:**
- Create: `src/lorairo/services/kohya_dataset_export_service.py`
- Test: `tests/integration/services/test_kohya_dataset_export_service.py`

**Interfaces:**
- 依存(Consumes): Task 3、7。保存済みオリジナル画像のパス解決は `DatasetExportService._get_image_export_data`(`dataset_export_service.py:1081`)の実装を確認して同じ方法を採用する。
- 提供(Produces):
  - `@dataclass(frozen=True) class KohyaExportResult: output_dir: Path; folder_count: int; image_count: int; text_count: int; dataset_config_path: Path; training_config_path: Path | None`
  - `class KohyaDatasetExportService`: `__init__(self, repository: DatasetRepository, ...)`、`export_version(self, version_id: int, output_dir: Path, *, training_config_id: int | None = None) -> KohyaExportResult`

書き出し規則は以下のとおりとする。
- `<output_dir>/<dir_name>/<file_stem><画像拡張子>` に画像をコピーし、`<file_stem><extension>` に学習テキストを書き出す。
- `is_edited` が偽の場合は `raw_text` を改行変換せず UTF-8(BOM なし、`newline=""`)でそのまま書き出す。真の場合は `join_elements(elements)` を書き出す。
- `dataset_config.toml` を `output_dir` 直下に書き出す。
- `training_config_id` が指定された場合は `training_config.toml` を書き出す(`path_overrides` は `train_data_dir=output_dir`、`output_dir=output_dir/"output"`、`logging_dir=output_dir/"logs"`)。
- 出力先ディレクトリがすでに存在し空でない場合は `FileExistsError` を送出する。

- [ ] **Step 1: 失敗するテストを書く**(Task 8 の取り込み結果を利用する)
  - `test_unedited_export_matches_raw_text_exactly`: CRLF、`(tag:1.2)`、大文字、アンダースコアを含む `.txt` が、書き出し後に `Path.read_text(encoding="utf-8", newline="")` で文字列一致することを検証する。
  - `test_edited_text_is_exported_from_elements`: `update_learning_text_elements` 後の書き出しが `join_elements` の結果になることを検証する。
  - `test_export_layout_and_images`: `10_a/x.png` と `5_b/x.png` が生成され、画像のバイト列が元と一致することを検証する。
  - `test_image_without_text_gets_no_text_file`: テキストの無い画像に対してテキストファイルが作られないことを検証する。
  - `test_dataset_config_toml_lists_subsets_with_repeats`: `toml.load` の結果で `num_repeats` が 10 と 5 であり、`caption_extension` が明示されていることを検証する。
  - `test_training_config_toml_overrides_paths`: パスが上書きされていることを検証する。
  - `test_non_empty_output_dir_raises`: 空でない出力先で `FileExistsError` が送出されることを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**
- [ ] **Step 4: テストを実行して通ることを確認する**
- [ ] **Step 5: コミットする** `feat: Kohya 形式の書き出し service を追加する`

---

### Task 10: CLI コマンドと往復の結合テスト

**Files:**
- Create: `src/lorairo/cli/commands/dataset.py`(`export.py` の Typer サブコマンド構成と `cli/main.py` への登録方法を踏襲する)
- Modify: `src/lorairo/cli/main.py`(登録のみ)
- Test: `tests/integration/cli/test_dataset_cli.py`、`tests/integration/services/test_dataset_roundtrip.py`

**Interfaces:**
- 依存(Consumes): Task 8、9
- 提供(Produces):
  - `lorairo-cli dataset import <DIR> --dataset NAME --version NAME [--parent-version ID] [--exclude-dir NAME ...] [--config FILE ...]`: スキャン結果から候補計画を作成してそのまま取り込む(確認ダイアログは GUI の Plan B で扱う)。
  - `lorairo-cli dataset export <VERSION_ID> <OUT_DIR> [--config-id ID]`
  - `lorairo-cli dataset show <VERSION_ID>`: フォルダ、繰り返し回数、画像数、トリガーワードを表示する。

- [ ] **Step 1: 失敗するテストを書く**
  - `test_cli_import_then_export_roundtrip`: CLI で取り込みから書き出しまでを行い、元の `.txt` と一致することを検証する(レビュー重点項目 4)。
  - `test_roundtrip_two_versions_with_parent`: 版 1 を取り込んだ後、`--parent-version` 指定で版 2 を取り込み、版 2 のスナップショットの `parent_version_id` が版 1 であることを検証する。
  - `test_cli_show_prints_folders`: `dataset show` がフォルダ情報を出力することを検証する。
  - `test_cli_import_missing_dir_exits_nonzero`: 存在しないディレクトリの取り込みで非ゼロ終了することを検証する。
- [ ] **Step 2: テストを実行して失敗を確認する**
- [ ] **Step 3: 実装する**(終了コードとエラー出力は `cli/_errors.py` の既存方式に従う)
- [ ] **Step 4: CI 相当フィルタで通過を確認する**(`uv run pytest tests/unit tests/integration -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 --timeout-method=thread`。`.claude/rules/testing.md` を参照)
- [ ] **Step 5: コミットする** `feat: データセットの取り込み・書き出し CLI を追加する`

---

### Task 11: ADR とドキュメント

**Files:**
- Create: `docs/decisions/<次の番号>-kohya-dataset-model.md`(番号は着手時に `ls docs/decisions`、`gh pr list`、`git branch -r` で他ブランチと衝突しない番号を選ぶ。現時点の最新は 0097)
- Modify: `docs/services.md`(新規サービスを一覧へ追加する)
- 索引(`docs/decisions/README.md`、`index.md`)は手編集せず `make adr-index` で再生成する。

- [ ] **Step 1: ADR を作成する**(Status は `Proposed` とする。設計書の §4、§9.5、§12 の決定を要約して設計書へリンクし、個別 Issue の解決記述を本文へ散りばめず `Related` にリンクのみ記載する)
- [ ] **Step 2: `docs/services.md` にサービスを追加し、`make adr-index` を実行する**
- [ ] **Step 3: `make format` と `make mypy` を実行して通過を確認する**
- [ ] **Step 4: コミットする** `docs: データセットモデルの ADR を追加する`

---

## 範囲外(本計画に含めない項目)

- GUI の取り込みダイアログ(Plan B。コアの API が固まってから別計画で実装する)。
- 通常ライブラリの取り込み時における共通タグ入力(Issue #1409)。
- 画像の追加・差し替え編集、版の比較、トリガーワードの自動付与。
- `LoRA_type` が `Standard` および `LyCORIS/LoCon` 以外の変換(`unmapped` に残す)。
- `ss_tag_frequency` や更新日時による元フォルダの自動特定。
