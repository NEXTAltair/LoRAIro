"""OpenAI Batch API応答のcontentテキストパーサー。

Batch APIレスポンスに含まれるcontent文字列から
tags/captionを構造化データに変換する。

対応フォーマット:
1. 標準(96.8%): "Tags: tag1, tag2\n\nCaption: text"
2. Markdownボールド(2.9%): "**Tags**: tag1\n\n**Caption**: text"
3. Markdownヘッダー(0.3%): "### Tags\n- tags\n\n### Caption\ntext"
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedAnnotationContent:
    """パース済みアノテーション内容。

    Attributes:
        tags: タグ文字列のリスト。
        caption: キャプションテキスト。欠落時はNone。
    """

    tags: list[str]
    caption: str | None


class BatchContentParser:
    """OpenAI Batch API応答のcontent文字列をパースする。"""

    # 標準フォーマット + Markdownボールド: "Tags:" or "**Tags**:"
    _TAGS_RE = re.compile(
        r"^(?:\*{0,2})Tags(?:\*{0,2})\s*:\s*(.+?)(?:\n\n|\n(?=(?:\*{0,2})Caption)|$)",
        re.DOTALL,
    )

    # Markdownヘッダーフォーマット: "### Tags"
    _HEADER_TAGS_RE = re.compile(
        r"###\s*Tags\s*\n(.*?)(?:\n\n|\n###|$)",
        re.DOTALL,
    )

    # Caption抽出: "Caption:" or "**Caption**:" or "### Caption"
    _CAPTION_RE = re.compile(
        r"(?:\*{0,2})Caption(?:\*{0,2})\s*:\s*(.+)",
        re.DOTALL,
    )
    _HEADER_CAPTION_RE = re.compile(
        r"###\s*Caption\s*\n(.+)",
        re.DOTALL,
    )

    @staticmethod
    def parse(content: str) -> ParsedAnnotationContent:
        """content文字列をパースしてタグとキャプションを抽出する。

        Args:
            content: OpenAI応答のcontent文字列。

        Returns:
            パース結果。

        Raises:
            ValueError: contentからタグを抽出できない場合。
        """
        if not content or not content.strip():
            raise ValueError("contentが空です")

        stripped = content.strip()

        # タグ抽出（ヘッダーフォーマット → 標準/ボールドフォーマットの順で試行）
        tags_raw: str | None = None
        is_header_format = False

        header_match = BatchContentParser._HEADER_TAGS_RE.search(stripped)
        if header_match:
            tags_raw = header_match.group(1)
            is_header_format = True
        else:
            tags_match = BatchContentParser._TAGS_RE.search(stripped)
            if tags_match:
                tags_raw = tags_match.group(1)

        if tags_raw is None:
            raise ValueError(f"タグセクションが見つかりません: {stripped[:100]}")

        # タグパース
        tags = BatchContentParser._parse_tags(tags_raw, is_header_format)
        if not tags:
            raise ValueError(f"有効なタグが見つかりません: {stripped[:100]}")

        # キャプション抽出
        caption: str | None = None
        if is_header_format:
            caption_match = BatchContentParser._HEADER_CAPTION_RE.search(stripped)
        else:
            caption_match = BatchContentParser._CAPTION_RE.search(stripped)

        if caption_match:
            caption = caption_match.group(1).strip()
            if not caption:
                caption = None

        return ParsedAnnotationContent(tags=tags, caption=caption)

    @staticmethod
    def _parse_tags(raw: str, is_header_format: bool) -> list[str]:
        """タグ文字列をリストに分解する。

        Args:
            raw: 生タグ文字列。
            is_header_format: Markdownヘッダーフォーマットかどうか。

        Returns:
            正規化されたタグリスト。
        """
        if is_header_format:
            # "- tag1\n- tag2" または "tag1, tag2" の両方に対応
            lines = raw.strip().split("\n")
            tags: list[str] = []
            for line in lines:
                # "- " プレフィクスを除去
                cleaned = re.sub(r"^[-*]\s*", "", line.strip())
                if cleaned:
                    # カンマ区切りの場合も処理
                    for t in cleaned.split(","):
                        t = t.strip()
                        if t:
                            tags.append(t)
            return tags
        else:
            # カンマ区切り
            return [t.strip() for t in raw.split(",") if t.strip()]
