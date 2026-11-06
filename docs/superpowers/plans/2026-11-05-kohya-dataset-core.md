# Kohya-ss データセットの取り込みと書き出し (コア) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kohya-ss 学習用データセットを、版・フォルダ・学習テキストとして取り込み、取り込み時と同じ形 (フォルダ + `.txt` + sd-scripts 用 TOML) で書き出せるコアを、Qt なしで作る。

**Architecture:** 新しい 6 テーブル (`datasets` `dataset_versions` `dataset_folders` `dataset_folder_images` `dataset_learning_texts` `training_configs`) と `DatasetRepository` を足す。取り込み・書き出し・設定の正規化は Qt-free の service とし、CLI から動かす。画像直下の `Tag` には一切書かない。GUI の取り込みダイアログは、このコアの API が固まってから別計画で作る (Plan B)。

**Tech Stack:** SQLAlchemy 2 / Alembic (SQLite)、Typer (CLI)、`toml` (既存依存)、pytest。

**Spec:** `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md` (以降「設計書」)。調査の数値は Issue #1404。

## Global Constraints

- 作業は `.agents/worktree/` 配下の worktree (`git worktree add .agents/worktree/kohya-ds -b feat/kohya-dataset-core origin/main`)。`uv run` は常にプロジェクトルートから実行 (CLAUDE.md)。
- Ruff 行長 108、全関数に型ヒント、`# type: ignore` / `# noqa` 禁止、`Any` を避ける、広い `except Exception` 禁止 (具体的な例外のみ)。
- docstring は Google style、実装コメントは日本語、ログは `from lorairo.utils.log import logger` (Loguru)。INFO はバッチ要約のみ、per-item は DEBUG。
- service は Qt-free (`src/lorairo/services/` に Qt を import しない)。Repository は `BaseRepository` を継承し `session_factory` を受け取る (ADR 0035)。
- Alembic の現在の head は `d4e5f6a7b8c9`。新しい migration の `down_revision` はこれ。SQLite は `batch_alter_table`、新規テーブルは `op.create_table`。`Base.metadata.create_all()` (テスト) と Alembic の両方で同じテーブルができること。
- 用語: データセット側は「学習テキスト」「要素」「トリガーワード」を使い、画像直下の「タグ」(`Tag`) と混ぜない (設計書 §0)。
- 取り込みで `TagCleaner.clean_format` を使わない。要素への分割はカンマと前後の空白の除去だけ (設計書 §4)。
- 秘密の値 (`*_api_key`、`*_token` で終わるキー) は保存も書き出しもしない。`raw_content` に残る値も空文字に置き換えてから保存する (設計書 §9.5)。
- 取り込む画像は各フォルダの**直下のみ**。`.txt` / `.caption` の既定の `caption_extension` は書き出し時に必ず明示する (sd-scripts の既定は `.caption`)。
- 版の `raw_text` は取り込み後に書き換えない。Repository に `raw_text` の更新 API を作らない。
- テストは `tests/unit` と `tests/integration`。カバレッジ 75% 以上。コミット末尾に `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`。
- 実データ (`H:\`) はこのコンテナから見えない。テストは `tmp_path` に実データの形を再現したフィクスチャで行う。

## Review Focus

1. 同じ画像が 2 つのフォルダにあり、別々の `.txt` を持つ → 学習テキストは別々のまま、`Tag` テーブルは 0 行 (Task 8)。
2. 作業用フォルダ (`sample001`、`終了`、`*__Processed`) と、フォルダ直下より深い画像は取り込まれない (Task 4, 8)。
3. 設定 json の空文字キーは出力されない。`wandb_api_key` の値は `raw_content` にも `normalized_json` にも残らない (Task 6)。
4. `(tag:1.2)`、大文字、アンダースコア、CRLF、複数行を含む `.txt` が、編集なしの書き出しで文字列として一致する (Task 9)。
5. `.txt` が無い画像は所属だけ記録され、書き出しで `.txt` を作らない。画像の無い `.txt` は無視する (Task 4, 9)。
6. 同じ版に二重に取り込む、同名のフォルダ・版を作ると、`DatasetConflictError` になり、中途半端な行が残らない (Task 3, 8)。

---

### Task 1: 学習テキストの要素分割と連結

**Files:**
- Create: `src/lorairo/services/learning_text.py`
- Test: `tests/unit/services/test_learning_text.py`

**Interfaces:**
- Produces: `split_elements(raw_text: str) -> list[str]`、`join_elements(elements: list[str]) -> str`

- [ ] **Step 1: 失敗するテストを書く**
  - `test_split_elements_keeps_case_underscore_and_parentheses`: `"Kariginu, long_sleeves, (tag:1.2), \\(x\\)"` → `["Kariginu", "long_sleeves", "(tag:1.2)", "\\(x\\)"]`。
  - `test_split_elements_drops_empty_items`: `"a,, b ,\n"` → `["a", "b"]`。
  - `test_split_elements_multiline_is_joined_by_comma_only`: 改行は要素の区切りにしない (改行を含む要素は 1 つとして残る)。`"a\nb, c"` → `["a\nb", "c"]`。
  - `test_join_elements_uses_comma_space`: `["a", "b"]` → `"a, b"`。
- [ ] **Step 2: 実行して失敗を確認** `uv run pytest tests/unit/services/test_learning_text.py -v` → FAIL (import error)。
- [ ] **Step 3: `split_elements` / `join_elements` を実装** (`str.split(",")` と `strip()` だけ。正規化しない)。
- [ ] **Step 4: 実行して通過を確認**。
- [ ] **Step 5: Commit** `feat: 学習テキストの要素分割と連結を追加する`

---

### Task 2: スキーマと Alembic migration

**Files:**
- Modify: `src/lorairo/database/schema.py` (クラスを `Project` の後ろに追加)
- Create: `src/lorairo/database/migrations/versions/<新rev>_add_dataset_tables.py` (`down_revision = "d4e5f6a7b8c9"`)
- Test: `tests/unit/database/test_dataset_schema.py`

**Interfaces:**
- Produces (すべて `Base` 継承、`Mapped[...]` スタイル。既存の `Project` を参照):
  - `Dataset`: `id`, `name` (UNIQUE, index), `description: str | None`, `created_at`
  - `DatasetVersion`: `id`, `dataset_id` (FK `datasets.id` CASCADE), `parent_version_id` (自己 FK, SET NULL, nullable), `name`, `created_at`。UNIQUE(`dataset_id`, `name`)
  - `DatasetFolder`: `id`, `version_id` (FK CASCADE), `dir_name` (例 `10_kariginu`), `name` (例 `kariginu`), `num_repeats: int`, `trigger_word: str | None`, `position: int`。UNIQUE(`version_id`, `dir_name`)
  - `DatasetFolderImage`: `id`, `folder_id` (FK CASCADE), `image_id` (FK `images.id` CASCADE), `file_stem: str`。UNIQUE(`folder_id`, `file_stem`)。index on `image_id`
  - `DatasetLearningText`: `id`, `folder_image_id` (FK CASCADE), `extension: str` (`.txt` / `.caption`), `raw_text: str` (Text), `elements_json: str` (Text, JSON の文字列リスト), `is_edited: bool` (default False)。UNIQUE(`folder_image_id`, `extension`)
  - `TrainingConfig`: `id`, `dataset_id` (FK CASCADE), `version_id` (FK SET NULL, nullable), `source_kind: str` (`kohya_gui_json` / `sd_scripts_toml` / `bat` / `safetensors_header`), `source_file_name: str`, `raw_content: str` (Text), `normalized_json: str` (Text), `unmapped_json: str` (Text), `target_script: str | None`, `output_name: str | None`, `base_model: str | None`, `resolution: str | None`, `network_dim: int | None`, `network_alpha: float | None`, `learning_rate: float | None`, `created_at`

- [ ] **Step 1: 失敗するテストを書く**
  - `test_create_all_creates_dataset_tables`: `Base.metadata.create_all(engine)` 後に `inspect(engine).get_table_names()` が 6 テーブルを含む。
  - `test_alembic_upgrade_head_creates_dataset_tables`: 既存の migration テスト (`grep -rn "command.upgrade" tests`) と同じ方法で一時 DB に `upgrade head` し、同じ 6 テーブルがある。
  - `test_alembic_has_single_head`: `ScriptDirectory.from_config(...).get_heads()` が要素 1 つ。
  - `test_deleting_version_cascades_to_folders_texts`: ORM で作って version を delete → folder / folder_image / learning_text が消える (SQLite で `PRAGMA foreign_keys=ON` になっている既存の接続設定を使う)。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 上のクラスを `schema.py` に、migration を新規ファイルに実装**。migration の docstring に Issue #1404 と設計書へのパスを書く。
- [ ] **Step 4: 通過を確認**。`uv run mypy -p lorairo` も通る。
- [ ] **Step 5: Commit** `feat: データセット関連テーブルと migration を追加する`

---

### Task 3: DatasetRepository

**Files:**
- Create: `src/lorairo/database/repository/dataset.py`
- Test: `tests/unit/database/repository/test_dataset_repository.py`

**Interfaces:**
- Consumes: Task 2 のモデル、`BaseRepository`
- Produces:
  - `class DatasetConflictError(ValueError)`
  - `@dataclass(frozen=True) class FolderSpec: dir_name: str; name: str; num_repeats: int; trigger_word: str | None; position: int`
  - `@dataclass(frozen=True) class LearningTextSpec: extension: str; raw_text: str; elements: list[str]`
  - `@dataclass(frozen=True) class FolderImageSpec: image_id: int; file_stem: str; texts: list[LearningTextSpec]`
  - `DatasetRepository.ensure_dataset(name: str, description: str | None = None) -> int`
  - `DatasetRepository.create_version(dataset_id: int, name: str, parent_version_id: int | None = None) -> int` (同名は `DatasetConflictError`)
  - `DatasetRepository.add_folder(version_id: int, spec: FolderSpec, images: list[FolderImageSpec]) -> int` (1 トランザクション。途中で失敗したら何も残らない)
  - `DatasetRepository.get_version_snapshot(version_id: int) -> VersionSnapshot` (`VersionSnapshot` は frozen dataclass: `dataset_name`, `version_name`, `parent_version_id`, `folders: list[FolderSnapshot]`。`FolderSnapshot` は `FolderSpec` の値 + `id` + `images: list[FolderImageSnapshot]`。画像は `image_id`, `file_stem`, `texts: list[LearningTextSnapshot]` (`id`, `extension`, `raw_text`, `elements`, `is_edited`))
  - `DatasetRepository.update_learning_text_elements(text_id: int, elements: list[str]) -> None` (`elements_json` を更新し `is_edited=True`。`raw_text` は変えない)
  - `DatasetRepository.set_folder_trigger_word(folder_id: int, trigger_word: str | None) -> None`
  - `DatasetRepository.add_training_config(dataset_id: int, version_id: int | None, spec: TrainingConfigSpec) -> int`、`list_training_configs(dataset_id: int) -> list[TrainingConfigSnapshot]`、`get_training_config(config_id: int) -> TrainingConfigSnapshot`。`TrainingConfigSpec` / `TrainingConfigSnapshot` は Task 2 の `TrainingConfig` の列と同名のフィールドを持つ frozen dataclass。

- [ ] **Step 1: 失敗するテストを書く** (`test_engine_with_schema` / `db_session_factory` フィクスチャを使い、`Image` 行は既存のヘルパーで 1 件作る)
  - `test_same_image_in_two_folders_keeps_separate_texts`: 同じ `image_id` を 2 つのフォルダに、別の `raw_text` で登録 → スナップショットの 2 フォルダで `raw_text` がそれぞれ異なる。
  - `test_create_version_with_same_name_raises_conflict`。
  - `test_add_folder_is_atomic`: 2 枚目の画像が不正な `image_id` (存在しない) → `IntegrityError` ではなく `DatasetConflictError` に変換するかは実装で決めてよいが、フォルダ行も 1 枚目の行も残らない。
  - `test_update_learning_text_elements_keeps_raw_text`: 更新後 `raw_text` は元のまま、`elements` が新しい、`is_edited` が True。
  - `test_version_parent_is_recorded`。
  - `test_training_config_roundtrip`: 追加して取得すると全フィールドが一致する。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装** (`json.dumps(..., ensure_ascii=False)` で `elements_json` を保存)。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: DatasetRepository を追加する`

---

### Task 4: Kohya ディレクトリのスキャナ

**Files:**
- Create: `src/lorairo/services/kohya_scanner.py`
- Test: `tests/unit/services/test_kohya_scanner.py`

**Interfaces:**
- Consumes: Task 1 の `split_elements`、`lorairo.utils.tools.decode_text_with_fallback`
- Produces:
  - `DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...]` = `("sample*", "終了", "*__Processed", "reg", "log", "logs", "wandb")` (`fnmatch`、フォルダ名に対して)
  - `@dataclass(frozen=True) class ScannedImage: path: Path; file_stem: str; texts: list[ScannedText]`、`ScannedText: extension: str; raw_text: str; elements: list[str]`
  - `@dataclass(frozen=True) class ScannedFolder: dir_path: Path; dir_name: str; name: str; num_repeats: int; images: list[ScannedImage]; trigger_candidate: str | None; trigger_match_rate: float`
  - `scan_kohya_directory(root: Path, exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS) -> list[ScannedFolder]`
  - `parse_folder_name(dir_name: str) -> tuple[int, str] | None` (`10_kariginu` → `(10, "kariginu")`、`abe no seimei` のようにスペースを含む名前も可。接頭辞が数字+`_` でなければ `None`)

- [ ] **Step 1: 失敗するテストを書く** (`tmp_path` に PIL で 8x8 の画像を作る小さなヘルパーを使う)
  - `test_parse_folder_name_extracts_repeats_and_name`: `"10_abe no seimei"` → `(10, "abe no seimei")`。`"sample001"` → `None`。
  - `test_scan_reads_only_direct_children_of_folders`: `root/10_a/x.png` は取り込み、`root/10_a/sub/y.png` は取り込まない。
  - `test_scan_skips_excluded_and_non_repeat_folders`: `sample001`、`終了`、`10_a__Processed`、`log` は結果に出ない。
  - `test_scan_reads_txt_and_caption_raw_text`: `x.txt` の `raw_text` は元のまま (CRLF を含む文字列で検証)。`.caption` は別の `ScannedText`。
  - `test_scan_image_without_text_has_empty_texts`: `.txt` の無い画像は `texts == []`。
  - `test_scan_ignores_text_without_image`。
  - `test_trigger_candidate_uses_most_common_first_element`: 5 枚中 5 枚が `kariginu` で始まる → `("kariginu", 1.0)`。5 枚中 1 枚だけ共通なら `trigger_match_rate` は 0.2 で、候補は `None` (閾値 0.5 以上で候補。閾値は定数 `TRIGGER_CANDIDATE_MIN_RATE = 0.5`)。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装** (画像拡張子は既存の定数を探して流用: `grep -rn "\.webp" src/lorairo | head`)。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: Kohya ディレクトリのスキャナを追加する`

---

### Task 5: sd-scripts の引数表

**Files:**
- Create: `scripts/gen_sd_scripts_arg_table.py` (開発用。`src` からは参照されない)
- Create: `src/lorairo/services/sd_scripts_arg_table.py` (生成物。先頭コメントに sd-scripts のコミット `cb70b96` と生成日を書く)
- Test: `tests/unit/services/test_sd_scripts_arg_table.py`

**Interfaces:**
- Produces: `SD_SCRIPTS_ARG_TYPES: dict[str, str]` (引数名 → `"int" | "float" | "str" | "bool"`。`type=` が無く `action="store_true"` / `"store_false"` なら `"bool"`、どれも無ければ `"str"`)

- [ ] **Step 1: 失敗するテストを書く**
  - `test_table_contains_known_args`: `learning_rate` → `"float"`、`network_dim` → `"int"`、`gradient_checkpointing` → `"bool"`、`optimizer_type` → `"str"`、`log_with` → `"str"`。
  - `test_table_excludes_launcher_and_gui_only_keys`: `num_cpu_threads_per_process`、`LoRA_type`、`sdxl` が無い。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 生成スクリプトを実装** (sd-scripts を `git fetch --depth 1 origin cb70b96` で空ディレクトリに取得し、`library/*.py`、`train_network.py`、`sdxl_train_network.py` を `ast` で読み、`add_argument` 呼び出しの最初の文字列定数 `--xxx` と `type=` / `action=` を集める。実行はせず読むだけ)。生成して `sd_scripts_arg_table.py` に書き出し、コミットする。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: sd-scripts の引数表を追加する`

---

### Task 6: Kohya_ss の設定 json の正規化

**Files:**
- Create: `src/lorairo/services/kohya_config_normalizer.py`
- Test: `tests/unit/services/test_kohya_config_normalizer.py`

**Interfaces:**
- Consumes: Task 5 の `SD_SCRIPTS_ARG_TYPES`
- Produces:
  - `@dataclass(frozen=True) class NormalizedConfig: raw_content: str; normalized: dict[str, str | int | float | bool | list[str]]; unmapped: dict[str, str | int | float | bool | list[str] | None]; target_script: str | None; output_name: str | None`
  - `normalize_kohya_gui_config(raw_text: str) -> NormalizedConfig` (`json.JSONDecodeError` はそのまま伝播)
  - `mask_secrets(config: dict[str, object]) -> dict[str, object]` (`*_api_key` / `*_token` で終わるキーの値を `""` にした新しい dict)

規則 (設計書 §9.5 と Issue #1404 のコメントが根拠。変換規則の出どころは Kohya_ss の `kohya_gui/lora_gui.py` と `common_gui.py` で、確認した版は `45088f0`。迷ったらその版のソースを読む):

| 入力 | 出力 |
|---|---|
| `""` / `None` の値 | 取り除く (`unmapped` にも入れない) |
| 秘密キー | `mask_secrets` で `raw_content` の値を空にし、`normalized` / `unmapped` に出さない |
| 起動ツール引数 (`extra_accelerate_launch_args` `gpu_ids` `main_process_port` `multi_gpu` `num_cpu_threads_per_process` `num_machines` `num_processes`) | 取り除く |
| `optimizer` / `sdxl_cache_text_encoder_outputs` / `sdxl_no_half_vae` / `lora_network_weights` / `max_resolution` | `optimizer_type` / `cache_text_encoder_outputs` / `no_half_vae` / `network_weights` / `resolution` に改名 |
| `use_wandb` が真 | `log_with = "wandb"`。偽なら取り除く |
| `lr_warmup` (比率 %) | `common_gui.py:1185` の `resolve_lr_warmup_steps` と同じ規則で `lr_warmup_steps` を作る。作れないときは `unmapped` |
| `sdxl` が真 | `target_script = "sdxl_train_network.py"`、偽/無しは `"train_network.py"`。`sdxl` キー自体は出さない |
| `LoRA_type == "Standard"` | `network_module = "networks.lora"` |
| `LoRA_type` が `"LyCORIS/LoCon"` / `"LoCon"` | `network_module = "lycoris.kohya"`、`network_args` は `lora_gui.py:1841-1843` の LoCon 用の組み立てと同じキー・順序の `["k=v", ...]` |
| その他の `LoRA_type` | `LoRA_type` と、その種類に関係する LyCORIS 系キーをすべて `unmapped` に残す |
| 上記以外で `SD_SCRIPTS_ARG_TYPES` にあるキー | そのまま出力。値は表の型に合わせて変換 (`"0.0001"` → `0.0001`、`"true"` → `True`) |
| 上記以外で表に無いキー | `unmapped` |

- [ ] **Step 1: 失敗するテストを書く** (入力は 1 つの辞書を `json.dumps` したもの)
  - `test_empty_string_keys_are_dropped`: `{"reg_data_dir": "", "dataset_config": ""}` → `normalized` / `unmapped` に出ない。
  - `test_secret_value_is_masked_everywhere`: `{"wandb_api_key": "SECRET"}` → `"SECRET"` が `raw_content` / `normalized` / `unmapped` の文字列表現のどこにも無い。
  - `test_renames_and_wandb_mapping`: `{"optimizer": "AdamW8bit", "use_wandb": true, "max_resolution": "1024,1024"}` → `normalized == {"optimizer_type": "AdamW8bit", "log_with": "wandb", "resolution": "1024,1024"}`。
  - `test_numeric_strings_are_coerced`: `{"learning_rate": "0.0001", "max_data_loader_n_workers": "0"}` → `0.0001` (float)、`0` (int)。
  - `test_sdxl_flag_selects_script`: `{"sdxl": true}` → `target_script == "sdxl_train_network.py"` で `"sdxl"` が `normalized` に無い。
  - `test_standard_lora_type_sets_network_module`。
  - `test_locon_packs_network_args`: `{"LoRA_type": "LyCORIS/LoCon", "conv_dim": 8, "conv_alpha": 1}` → `network_module == "lycoris.kohya"`、`network_args` に `"conv_dim=8"` と `"algo=locon"` が含まれる。
  - `test_other_lora_type_goes_to_unmapped`: `{"LoRA_type": "LyCORIS/LoHa"}` → `unmapped["LoRA_type"] == "LyCORIS/LoHa"` で `network_module` が `normalized` に無い。
  - `test_output_name_is_extracted`。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装**。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: Kohya_ss 設定 json の正規化を追加する`

---

### Task 7: sd-scripts 用 TOML の書き出し関数

**Files:**
- Create: `src/lorairo/services/sd_scripts_toml.py`
- Test: `tests/unit/services/test_sd_scripts_toml.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class SubsetSpec: image_dir: Path; num_repeats: int; caption_extension: str`
  - `render_dataset_config(subsets: list[SubsetSpec]) -> str` (`[general] caption_extension`、`[[datasets]]`、`[[datasets.subsets]]` に `image_dir` `num_repeats` `caption_extension`。`caption_extension` は必ず明示)
  - `render_training_config(normalized: dict[str, str | int | float | bool | list[str]], path_overrides: dict[str, Path]) -> str` (フラットな TOML。`path_overrides` のキー (`train_data_dir` `output_dir` `logging_dir` など) は値を文字列に置き換えて書く。`reg_data_dir` は上書きされない限り出さない。`toml.dumps` を使う)

- [ ] **Step 1: 失敗するテストを書く**
  - `test_dataset_config_has_explicit_caption_extension`: `toml.loads` の結果で `general.caption_extension` と、各 subset の `caption_extension` が `".txt"`。
  - `test_dataset_config_subsets`: 2 つの `SubsetSpec` → `datasets[0].subsets` が 2 件で、`num_repeats` と `image_dir` が一致。
  - `test_training_config_is_flat_and_overrides_paths`: `normalized` に `train_data_dir = "/old"` があり、`path_overrides={"train_data_dir": Path("/new")}` → 出力の `train_data_dir == "/new"`、セクション (`[...]`) が無い。
  - `test_training_config_omits_reg_data_dir_unless_given`。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装**。**検証**: sd-scripts の `library/config_util.py` を読み、`--dataset_config` を使うとき `resolution` / `batch_size` / `enable_bucket` が引数側から補われることを確認する。補われないなら、`render_dataset_config` に `resolution: str | None` など 3 つの任意引数を足して `[[datasets]]` に書く。確認結果を関数の docstring に一行で残す。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: sd-scripts 用 TOML の書き出し関数を追加する`

---

### Task 8: 取り込み service

**Files:**
- Create: `src/lorairo/services/dataset_import_service.py`
- Test: `tests/integration/services/test_dataset_import_service.py`

**Interfaces:**
- Consumes: Task 1, 3, 4, 6。`ImageDatabaseManager.register_original_image(image_path, fsm) -> tuple[int, dict[str, Any]] | None` (**`register_image_with_side_effects` は使わない**。`Tag` に書いてしまうため)
- Produces:
  - `@dataclass(frozen=True) class FolderImportPlan: dir_name: str; name: str; num_repeats: int; trigger_word: str | None; include: bool`
  - `@dataclass(frozen=True) class DatasetImportPlan: dataset_name: str; version_name: str; parent_version_id: int | None; folders: list[FolderImportPlan]; config_files: list[Path]`
  - `@dataclass(frozen=True) class DatasetImportResult: dataset_id: int; version_id: int; folder_count: int; image_count: int; skipped_images: int; training_config_ids: list[int]`
  - `class DatasetImportService: __init__(self, db_manager: ImageDatabaseManager, repository: DatasetRepository, fsm: FileSystemManager)`、`import_directory(self, root: Path, plan: DatasetImportPlan) -> DatasetImportResult`、`propose_plan(self, root: Path, dataset_name: str, version_name: str) -> DatasetImportPlan` (スキャン結果と、`root` 直下の `*.json` の `output_name` から版名の候補を作る。確定はしない)

- [ ] **Step 1: 失敗するテストを書く** (`tmp_path` に Kohya 形のディレクトリを作る: `10_a/` と `5_b/` の 2 フォルダ、同じ画像ファイルを両方に置き `.txt` を別の内容にする、`sample001/` に画像、`10_a/` に `.caption` だけの画像と、`.txt` が無い画像)
  - `test_same_image_in_two_folders_keeps_separate_texts_and_no_tags`: 取り込み後、スナップショットの 2 フォルダで同じ `image_id` を持ち、`raw_text` が別。`SELECT count(*) FROM tags` が 0。
  - `test_excluded_folders_are_not_imported`: `sample001` の画像は `images` に増えない。
  - `test_image_without_text_is_member_without_text`。
  - `test_trigger_word_is_stored_only_from_plan`: `plan.folders[i].trigger_word` が保存され、スキャンの候補は保存されない。
  - `test_duplicate_import_into_same_version_raises_conflict_and_leaves_no_rows`。
  - `test_config_json_is_stored_with_masked_secret`: `config_files` の json (`wandb_api_key` を含む) → `training_configs` の `raw_content` に秘密の値が無い。
  - `test_propose_plan_uses_output_name_as_version_hint`。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装** (1 フォルダごとに `add_folder` を 1 トランザクションで。画像の登録失敗 (`register_original_image` が `None`) は `skipped_images` に数え、ログは DEBUG)。`config_files` は `source_kind="kohya_gui_json"` として `normalize_kohya_gui_config` に通し、`TrainingConfigSpec` の `output_name` `base_model` (`pretrained_model_name_or_path`) `resolution` `network_dim` `network_alpha` `learning_rate` は `normalized` から取り出す (無ければ `None`)。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: データセットの取り込み service を追加する`

---

### Task 9: 書き出し service

**Files:**
- Create: `src/lorairo/services/kohya_dataset_export_service.py`
- Test: `tests/integration/services/test_kohya_dataset_export_service.py`

**Interfaces:**
- Consumes: Task 3, 7。保存済みオリジナル画像のパス解決は `DatasetExportService._get_image_export_data` (`dataset_export_service.py:1081`) の方法を読んで同じものを使う。
- Produces:
  - `@dataclass(frozen=True) class KohyaExportResult: output_dir: Path; folder_count: int; image_count: int; text_count: int; dataset_config_path: Path; training_config_path: Path | None`
  - `class KohyaDatasetExportService: __init__(self, repository: DatasetRepository, ...)`、`export_version(self, version_id: int, output_dir: Path, *, training_config_id: int | None = None) -> KohyaExportResult`

規則: `<output_dir>/<dir_name>/<file_stem><画像拡張子>` に画像をコピー、`<file_stem><extension>` に学習テキストを書く。`is_edited` が偽なら `raw_text` を**そのまま** (改行を変換せず、UTF-8 BOM 無し、`newline=""`)、真なら `join_elements(elements)`。`dataset_config.toml` を `output_dir` 直下に書く。`training_config_id` があれば `training_config.toml` を書く (`path_overrides` は `train_data_dir=output_dir`、`output_dir=output_dir/"output"`、`logging_dir=output_dir/"logs"`)。出力先が既に存在し空でなければ `FileExistsError`。

- [ ] **Step 1: 失敗するテストを書く** (Task 8 の取り込み結果を使う)
  - `test_unedited_export_matches_raw_text_exactly`: CRLF・`(tag:1.2)`・大文字・アンダースコアを含む `.txt` が、書き出し後に文字列として一致する (`Path.read_text(encoding="utf-8", newline="")`)。
  - `test_edited_text_is_exported_from_elements`: `update_learning_text_elements` 後は `join_elements` の結果。
  - `test_export_layout_and_images`: `10_a/x.png` と `5_b/x.png` ができ、画像バイト列が元と一致する。
  - `test_image_without_text_gets_no_text_file`。
  - `test_dataset_config_toml_lists_subsets_with_repeats`: `toml.load` で `num_repeats` が 10 と 5、`caption_extension` が明示されている。
  - `test_training_config_toml_overrides_paths`。
  - `test_non_empty_output_dir_raises`。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装**。
- [ ] **Step 4: 通過を確認**。
- [ ] **Step 5: Commit** `feat: Kohya 形式の書き出し service を追加する`

---

### Task 10: CLI コマンドと往復の結合テスト

**Files:**
- Create: `src/lorairo/cli/commands/dataset.py` (`export.py` の Typer サブコマンドの作り方と、`cli/main.py` への登録方法を踏襲する)
- Modify: `src/lorairo/cli/main.py` (登録のみ)
- Test: `tests/integration/cli/test_dataset_cli.py`、`tests/integration/services/test_dataset_roundtrip.py`

**Interfaces:**
- Consumes: Task 8, 9
- Produces:
  - `lorairo-cli dataset import <DIR> --dataset NAME --version NAME [--parent-version ID] [--exclude-dir NAME ...] [--config FILE ...]`: スキャン結果から候補の計画を作り、そのまま取り込む (確認ダイアログは GUI の Plan B)。
  - `lorairo-cli dataset export <VERSION_ID> <OUT_DIR> [--config-id ID]`。
  - `lorairo-cli dataset show <VERSION_ID>`: フォルダ、繰り返し回数、画像数、トリガーワードを表示。

- [ ] **Step 1: 失敗するテストを書く**
  - `test_cli_import_then_export_roundtrip`: CLI で取り込み → 書き出し → 元の `.txt` と一致 (Review Focus 4)。
  - `test_roundtrip_two_versions_with_parent`: 版 1 を取り込み、`--parent-version` で版 2 を取り込む → 版 2 のスナップショットの `parent_version_id` が版 1。
  - `test_cli_show_prints_folders`。
  - `test_cli_import_missing_dir_exits_nonzero`。
- [ ] **Step 2: 失敗を確認**。
- [ ] **Step 3: 実装** (終了コード・エラー出力は `cli/_errors.py` の既存方式)。
- [ ] **Step 4: 通過を確認** `uv run pytest tests/unit tests/integration -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 --timeout-method=thread` (CI と同じ filter。`.claude/rules/testing.md` 参照)。
- [ ] **Step 5: Commit** `feat: データセットの取り込み・書き出し CLI を追加する`

---

### Task 11: ADR とドキュメント

**Files:**
- Create: `docs/decisions/<次の番号>-kohya-dataset-model.md` (番号は着手時に `ls docs/decisions` と `gh pr list` / `git branch -r` で、他の着手中のブランチと衝突しないものを選ぶ。現時点の最新は 0097)
- Modify: `docs/services.md` (新しい service を一覧に追加)
- 索引 (`docs/decisions/README.md`, `index.md`) は手編集せず `make adr-index` で再生成

- [ ] **Step 1: ADR を書く** (Status は `Proposed`。内容は設計書の §4・§9.5・§12 の決定を要約し、設計書へリンクする。個別 Issue の解決を本文に散りばめず、Related にリンクだけ)。
- [ ] **Step 2: `docs/services.md` に service を追加し、`make adr-index` を実行**。
- [ ] **Step 3: `make format` / `make mypy` を実行して通過を確認**。
- [ ] **Step 4: Commit** `docs: データセットモデルの ADR を追加する`

---

## 範囲外 (この計画に含めない)

- GUI の取り込みダイアログ (Plan B。コアの API が固まってから別計画)。
- 普段のライブラリの取り込み時の共通タグ入力 (Issue #1409)。
- 画像の追加・差し替えの編集、版の比較、トリガーワードの自動付与。
- `LoRA_type` が `Standard` / `LyCORIS/LoCon` 以外の変換 (`unmapped` に残す)。
- `ss_tag_frequency` や更新日時による元フォルダの自動特定。
