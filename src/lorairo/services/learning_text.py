"""学習テキスト (Kohya-ss データセットの .txt / .caption) の要素分割と連結。

画像直下のタグ (Tag) とは別物として扱うため、正規化 (小文字化、アンダースコア変換等) は行わない。
"""


def split_elements(raw_text: str) -> list[str]:
    """学習テキストをカンマ区切りの要素に分割する。

    カンマと前後の空白の除去だけを行い、大文字小文字や記号は保持する。
    空の要素は捨てる。改行は区切りとして扱わない。

    Args:
        raw_text: 学習テキストの原文。

    Returns:
        要素の文字列リスト。
    """
    # カンマで分割し、前後の空白だけ除去する (正規化しない)
    return [element for element in (part.strip() for part in raw_text.split(",")) if element]


def join_elements(elements: list[str]) -> str:
    """要素リストを「, 」区切りの学習テキストに連結する。

    Args:
        elements: 要素の文字列リスト。

    Returns:
        連結した学習テキスト。
    """
    return ", ".join(elements)
