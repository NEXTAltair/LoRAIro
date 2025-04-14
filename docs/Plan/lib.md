**必須ライブラリ:**

- 画像処理: `Pillow`, `opencv-python`, `numpy`
- AI/機械学習: `transformers`, `diffusers`, `torch`, `torchvision`, `torchaudio`, `pytorch-lightning`
- データ処理: `SQLAlchemy`, `Polars`
- GUI: `PySide6`, `superqt`
- API 通信: `requests`
- 設定ファイル: `toml`

**不要ライブラリ:**

- `PyYAML`
- `ImageHash`, `Imagededup`, `vptree` (重複検知ライブラリは後ほど選定)
- `google-generativeai`, `anthropic`, `openai` (これらは`dataset-tag-editor-standalone`内で使用されるため、直接 LoRAIro に含める必要はない)
- `timm`, `spandrel` (必要に応じて後で追加)
- `gradio` (PySide6 に絞るため)

**開発ツール (必要に応じて):**

- `pytest`, `pytest-cov`, `pytest-qt`, `ruff`, `isort`, `mypy`, `sphinx`, `sphinx-rtd-theme`, `sphinx-autobuild`, `restructuredtext_lint`, `joblib`

**自作ライブラリ:**

- `genai-tag-db-tools`, `dataset-tag-editor-standalone`

**今後の検討事項:**

- 重複検知ライブラリの選定: `ImageHash`, `Imagededup`, `vptree` から選択、または別のライブラリを検討。
- 必要に応じて `timm`, `spandrel` を追加。
- 設定ファイル形式の最終決定 (TOML で問題なければそのまま使用)。
