# Session: アノテーション結果表示UI 3方式比較・実装

**Date**: 2026-02-15
**Branch**: feature/annotation-base
**Status**: completed

---

## 実装結果

### 根本原因特定: PYTHONPATH汚染問題
- **問題**: 3つのworktreeで実装したUI変更が一切表示されない
- **根本原因**: `.devcontainer/Dockerfile` に `PYTHONPATH` がハードコードされており、全worktreeでメインリポジトリ(`/workspaces/LoRAIro/src`)が常に優先される
- **解決方法**: 各worktreeから起動時に `PYTHONPATH="" VIRTUAL_ENV=""` を設定してメインリポジトリのパスを上書き

### 修正と統合
1. **Worktree B（方式B：5タブダイアログ）の Pydantic バグ修正**
   - `UnifiedAnnotationResult` は Pydantic モデルのため `.get()` 不可
   - `getattr()` に変更（コミット: `f2e8a37`）
   - 存在しない `formatted_output` フィールド参照を削除、直接 `tags/captions/scores` 属性に変更

2. **方式B のマージ**
   - `feature/annotation-ui-b` を `feature/annotation-base` にマージ（コミット: `0e68319`）
   - マージコミットメッセージ: "merge: 方式B(5タブ拡張ダイアログ)をアノテーション結果表示として採用"

3. **Worktree クリーンアップ**
   - Worktree A（サマリーダイアログ+独立ウィンドウ）削除
   - Worktree C（MainWindowタブ統合）削除
   - Worktree B（採用方式）削除
   - ブランチ `feature/annotation-ui-b` 削除（コミットはマージで統合済み）

### 最終状態
```
/workspaces/LoRAIro (feature/annotation-base)
  ├─ コミット 79f50a2: アノテーション結果表示の共通基盤を実装
  ├─ コミット 25ca601: 方式B - AnnotationSummaryDialogを5タブ構成に拡張
  ├─ コミット f2e8a37: UnifiedAnnotationResult Pydantic属性アクセスエラー修正
  └─ コミット 0e68319: merge - 方式B採用
```

---

## 設計意図と判断

### なぜ方式Bを採用したか
- **サマリータブ**: 統計情報をコンパクトに表示（統計→結果確認の自然な流れ）
- **5タブ構成**: タグ/キャプション/スコア/モデル詳細を分離。タブで簡単に切り替え可能
- **ユーザビリティ**: ダイアログ内に全情報が集約されており、別ウィンドウ管理の煩雑さがない
- **メンテナンス性**: 単一ダイアログで完結（方式A の複数ウィンドウ管理より簡潔）

### 検討した代替案と却下理由
- **方式A（サマリー+独立ウィンドウ）**: ウィンドウが増えるため、ユーザーに分散操作を強いる
- **方式C（MainWindowタブ）**: アノテーション後の他操作との並行性は高いが、タブ切り替えの手数が増える

---

## 問題と解決

### 1. PYTHONPATH環境変数の優先度問題
**問題**: 各worktreeの独立した`.venv`を作成しても、Dockerfileのハードコードされた`PYTHONPATH`がsys.path[1-3]に常に注入される

**解決方法**:
```bash
# 起動コマンド前に環境変数をクリア
PYTHONPATH="" VIRTUAL_ENV="" .venv/bin/lorairo
```

**検証**:
```python
# worktree固有のコードが正しくロードされることを確認
cd /workspaces/LoRAIro-annotation-ui-b
PYTHONPATH="" VIRTUAL_ENV="" .venv/bin/python -c "
import lorairo.gui.widgets.annotation_summary_dialog as m
print(m.__file__)  # → /workspaces/LoRAIro-annotation-ui-b/src/...
"
```

### 2. UnifiedAnnotationResult のPydantic属性アクセス
**問題**: Worktree B で `result.get("tags", [])` を実行→ AttributeError
```
AttributeError: 'UnifiedAnnotationResult' object has no attribute 'get'
```

**原因**: `UnifiedAnnotationResult` は Pydantic モデル（dataclass ではなく）。dict風の `.get()` メソッドが存在しない

**解決方法**: `getattr(result, "tags", None)` に変更
```python
# Before (NG)
tags = result.get("tags", [])

# After (OK)
tags = getattr(result, "tags", None) or []
```

### 3. 存在しないフィールド参照
**問題**: `formatted_output` フィールドを参照→ AttributeError

**根本原因**: `UnifiedAnnotationResult` の実際のフィールド:
- `tags`, `captions`, `scores` ✓ 存在
- `formatted_output` ✗ 存在しない

**解決方法**: 直接属性を参照
```python
captions = getattr(result, "captions", None)
scores = getattr(result, "scores", None)
```

---

## 技術的な学び

### Pydantic モデルとdict属性アクセスの違い
- **Pydantic モデル**: `obj.field` で属性アクセス。`.get()` メソッドなし
- **dict**: `d["key"]` または `d.get("key", default)` でアクセス
- **混在対応**: `getattr(obj, "field", None)` で両対応可能

### Dockerfileハードコード環境変数の影響
- devcontainer の`ENV PYTHONPATH=...` は全worktreeで有効
- `.venv` の `.pth` ファイルより `PYTHONPATH` が優先度高
- ワークツリー単位で異なるコードを実行する場合は、起動時に `PYTHONPATH=""` でクリアが必須

---

## 未完了・次のステップ

### 1. Step 0（ローカルモデル capabilities 修正）
前のセッションの大規模計画 (`cached-mapping-squirrel.md`) で定義されている Step 0 はまだ未実装:
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/utils.py` の `get_model_capabilities()` にフォールバック推論追加
- `config/annotator_config.toml` と `local_packages/.../system/annotator_config.toml` に `capabilities` フィールド追加
- 既存の誤った `capabilities` 設定（aesthetic_shadow等）の修正

### 2. feature/annotation-base の mainへのマージ
- 現在 `feature/annotation-base` で成功しているコミット（共通基盤 + 方式B）を main にマージ
- または先に Step 0 を mainで実装してから feature/annotation-base を main に マージ

### 3. X11フォワーディング設定
- Windows 側で VcXsrv または XLaunch 起動が必要な状態（前セッションから）
- GUI 表示テスト時は Docker の DISPLAY 環境変数設定が必要

---

## 関連するメモリファイル

- `plan_zesty_doodling_brooks_2026_02_13.md` - 3方式UI比較の計画
- `cached-mapping-squirrel.md` - 大規模アノテーション結果表示UX改善計画（Step 0未実装）
- `rosy-stirring-bumblebee.md` - sys.path優先度問題の修正計画（本セッションで実装）
