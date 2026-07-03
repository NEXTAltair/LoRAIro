"""ImageFilterCriteria - データベースフィルタリング専用の条件クラス

このモジュールはデータベース層で使用される画像フィルタリング条件を定義します。
GUI/ServiceレイヤーのSearchConditionsとは分離され、DB操作の明確な契約を提供します。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeywordSearchGroup:
    """1 つの入力キーワードに対する検索対象語群 (#1093/#1094)。

    タグ / キャプションを独立した検索対象として持ち、翻訳エイリアスを保持する。
    SQL では ``tag_terms`` 内 (エイリアス群) は OR、``caption_terms`` 内も OR、
    そして 1 キーワードとして ``(tag_terms のいずれか OR caption_terms のいずれか)`` で
    マッチ判定する。キーワード間は ``ImageFilterCriteria.use_and`` に従い AND / OR で結合する。

    Attributes:
        tag_terms: このキーワードのタグ検索対象 (元語 + 翻訳エイリアス、OR 判定)。
            タグが検索対象でない場合は空リスト。
        caption_terms: このキーワードのキャプション検索対象 (OR 判定)。
            キャプションが検索対象でない場合は空リスト。
    """

    tag_terms: list[str] = field(default_factory=list)
    caption_terms: list[str] = field(default_factory=list)


@dataclass
class ImageFilterCriteria:
    """データベース層の画像フィルタリング条件

    DB Repository/Manager層で使用される画像検索条件を表すデータクラス。
    すべてのパラメータにデフォルト値を持ち、部分的な条件指定が可能です。

    Attributes:
        tags: 検索するタグのリスト
        caption: 検索するキャプションキーワードのリスト (全語を対象、#1093)
        excluded_tags: 除外するタグのリスト（NOT検索）
        resolution: 検索対象の解像度(長辺)、0の場合はオリジナル画像
        use_and: 複数タグ指定時の検索方法 (True: AND, False: OR)
        start_date: 検索開始日時 (ISO 8601形式)
        end_date: 検索終了日時 (ISO 8601形式)
        include_untagged: タグが付いていない画像のみを対象とするか
        include_nsfw: NSFWコンテンツを含む画像を除外しないか
        include_unrated: 未評価画像を含めるか (False: 手動またはAI評価のいずれか1つ以上を持つ画像のみ)
        only_unrated: rating が無い画像のみを対象とするか
        missing_model_litellm_id: 指定モデルのannotation行が無い画像のみを対象とするか
        manual_rating_filter: 指定した手動レーティングを持つ画像のみを対象とするか。
            単一値 (str) または複数値 (list[str]) を受け付ける。複数値は選択集合の
            OR (いずれかに一致) として扱う (Issue #811 マルチセレクト chip)。番兵
            "UNRATED" (手動レーティングなし) / "RATED" (手動レーティングあり) を
            通常値と併用した場合も同じ集合内 OR で合成する。
        ai_rating_filter: 指定したAI評価レーティングを持つ画像のみを対象とするか (多数決ロジック)。
            単一値 (str) または複数値 (list[str]) を受け付ける。複数値は選択集合の
            OR として扱い、多数決は「選択集合のいずれかに一致する評価」を母数に判定する。
        rating_combine: manual_rating_filter と ai_rating_filter の組合せ方。
            "and" (デフォルト, 両方を満たす) または "or" (いずれかを満たす)。両方が
            指定されたときのみ意味を持ち、片方のみ指定時は常に AND と等価。
        manual_edit_filter: アノテーションが手動編集されたかでフィルタするか
        score_min: 最小スコア値（0.0-10.0）
        score_max: 最大スコア値（0.0-10.0）
        project_name: フィルタ対象プロジェクト名（Phase C完了後に有効化）
        project_id: フィルタ対象プロジェクトID（Phase C完了後に高速路）
        limit: 取得件数上限。None の場合は無制限
        offset: 取得開始位置
        image_ids: 明示的な画像IDリスト。指定時は exact-set selector として扱い、
            他のフィルタ次元（tags / caption / include_nsfw / rating / score 等）を
            すべてバイパスして指定IDをそのまま対象にする（ADR 0055）。GUI が
            ステージング集合を criteria 経由でエクスポートする際に使用する。
            最大 ImageRepository.EXACT_SET_MAX_IDS 件（= ステージング上限 500）。
            超過時は ValueError（ADR 0056）。
        sort_field: ソートキー。"image_id"（デフォルト）または "file_path"。
        sort_direction: ソート方向。"asc"（デフォルト）または "desc"。
    """

    tags: list[str] | None = None
    caption: list[str] | None = None
    excluded_tags: list[str] | None = None
    # #1093/#1094: per-keyword の検索対象語群。指定時は tags / caption のフラットな
    # positive マッチを置き換え、各キーワードが (tag OR caption) にマッチする条件を
    # use_and で結合する (タグの翻訳エイリアスはキーワード内 OR)。excluded_tags は
    # 従来どおり別途 NOT EXISTS で AND 適用する。GUI 検索フローが使用し、export / CLI 等の
    # フラット検索は None のまま従来経路を通る。
    keyword_groups: list[KeywordSearchGroup] | None = None
    resolution: int = 0
    use_and: bool = True
    start_date: str | None = None
    end_date: str | None = None
    include_untagged: bool = False
    include_nsfw: bool = False
    include_unrated: bool = True
    only_unrated: bool = False
    missing_model_litellm_id: str | None = None
    manual_rating_filter: str | list[str] | None = None
    ai_rating_filter: str | list[str] | None = None
    # Issue #811: manual / AI レーティングフィルタの組合せ方 ("and" | "or")
    rating_combine: str = "and"
    manual_edit_filter: bool | None = None
    score_min: float | None = None
    score_max: float | None = None
    # Phase 4: Search サイドバー強化 facets
    reviewed_at_filter: str | None = None  # "unreviewed" | "reviewed" | None=全て
    error_state_filter: str | None = None  # "has_error" | "no_error" | None=全て
    model_filter: list[str] | None = None  # litellm_id リスト。None=全モデル
    # Phase C (projects テーブル追加) 完了後に DB フィルタを有効化
    project_name: str | None = None
    project_id: int | None = None
    limit: int | None = None
    offset: int = 0
    # Issue #965: 検索フェーズでアノテーション (tags/captions/scores/score_labels/
    # ratings) を先読みするか。False の場合は id + 各テーブルカラムのみ取得し、
    # アノテーションは選択 → プレビュー表示時に遅延取得する (検索→レビュー表示の高速化)。
    include_annotations: bool = True
    # ADR 0055: 指定時は他フィルタを bypass する exact-set selector
    image_ids: list[int] | None = None
    # Issue #697: images search で使用するソート条件
    sort_field: str = "image_id"  # "image_id" または "file_path"
    sort_direction: str = "asc"  # "asc" または "desc"
