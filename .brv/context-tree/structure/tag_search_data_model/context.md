
## Relations
@@design/tag_search_results_layout
@@testing/tag_search_widget_tests

TagRecordPublic now carries deprecated; converters output alias/deprecated;

---

class TagRecordPublic(BaseModel):
    """検索結果の1行（外部向け / IDなし）。

    Args:
        tag: 表示用の正規タグ。
        source_tag: ソースタグ（あれば）。
        format_name: フォーマット名。
        type_name: タイプ名。
        alias: エイリアスかどうか。
    """

    tag: str = Field(..., description="表示用の正規タグ")
    source_tag: str | None = Field(default=None, description="ソースタグ")
    format_name: str | None = Field(default=None, description="フォーマット名")
    type_id: int | None = Field(default=None, description="タイプID")
    type_name: str | None = Field(default=None, description="タイプ名")
    alias: bool | None = Field(default=None, description="エイリアスかどうか")
    deprecated: bool | None = Field(default=None, description="非推奨かどうか")
    usage_count: int | None = Field(default=None, description="????")
    translations: dict[str, list[str]] | None = Field(
        default=None, description="言語別の翻訳一覧"
    )
    format_statuses: dict[str, dict[str, object]] | None = Field(
        default=None, description="フォーマット別の状態一覧"
    )
