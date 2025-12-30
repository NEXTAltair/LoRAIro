# genai-tag-db-tools CI Workflow Update

## 変更日時
2025-12-27

## 対象ファイル
`.github/workflows/python-package.yml`

## 変更内容
pytest実行ステップに `CI: true` 環境変数を追加:

```yaml
- name: Test with pytest
  env:
    CI: true  # 追加
    QT_QPA_PLATFORM: offscreen
    QTWEBENGINE_DISABLE_SANDBOX: 1
    HF_HUB_OFFLINE: 1
  run: uv run pytest --cov=src/genai_tag_db_tools --cov-report=xml --cov-report=term -m "not slow and not network"
```

## 目的
`requires_real_db` マーカーが付いたテストをCI環境でスキップするため。

conftest.py の `reset_runtime_for_real_db` フィクスチャが `os.environ.get("CI") == "true"` をチェックし、CI環境では `pytest.skip()` を実行する。

## 動作
- **CI環境** (`CI=true`): `requires_real_db` マーカー付きテストをスキップ（DBダウンロード不要）
- **ローカル環境** (CI環境変数なし): `requires_real_db` マーカー付きテストを実行（実際のDBダウンロード + 統合テスト）

## 関連ファイル
- `/workspaces/LoRAIro/local_packages/genai-tag-db-tools/tests/conftest.py`
- `.serena/memories/genai_tag_db_tools_test_quality_fix_completion_2025_12_28`
