"""出力タグオーバーレイ適用ロジック（Qt-free）。

ADR 0080 §1-§4 に従い、export 時の per-image タグ変換パイプラインを実装する。

パイプライン順序（ADR 0080 §2）:
    db_tags（convert 前・採用タグ）
    1. replace 適用（X→Y）
    2. exclude 除去
    3. convert（alias→preferred + meta 除外。reader=None なら素通し）
    4. add を先頭に literal prepend（convert バイパス）
    5. 順序保持 dedup（先頭=trigger 側を優先して残す）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from genai_tag_db_tools import convert_tags

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader


@dataclass
class ExportTagOverlay:
    """1 つの overlay ルールが持つタグ変換指示。Qt-free・immutable-friendly。

    Attributes:
        add: 先頭に literal prepend する trigger word 等。convert を通さない。
        exclude: 出力から除外するタグ名の集合。convert 前に適用する。
        replace: 1:1 置換マッピング（X→Y）。convert 前に適用する。
            削除したいタグは exclude に指定する（to が非空である前提）。
    """

    add: list[str]
    exclude: set[str]
    replace: dict[str, str]

    @property
    def is_noop(self) -> bool:
        """overlay が全操作とも空（add/exclude/replace 全て空）かどうかを返す。

        True の場合、apply_overlay を通しても convert/dedup 以外の変化はない。
        スコープ外画像でのレガシーパスへのフォールバック判定に使用する（ADR 0080 §2）。
        """
        return not self.add and not self.exclude and not self.replace


@dataclass
class ScopedOverlayRule:
    """スコープ付き overlay ルール。image_ids=None は全 staging 画像に適用。

    Attributes:
        image_ids: 適用対象の image_id 集合。None = 全画像（グローバルスコープ）。
        overlay: 適用する ExportTagOverlay。
    """

    image_ids: set[int] | None
    overlay: ExportTagOverlay


@dataclass
class ExportOverlayPlan:
    """export 全体に適用する overlay ルール集合。

    effective_for(image_id) で image_id に該当するルールを積み上げ合成し、
    実効 ExportTagOverlay を返す（ADR 0080 §3）。

    合成ルール:
        - add: ルール定義順に連結（global → subset）。最終 dedup で重複を畳む。
        - exclude: 全該当ルールの和集合。
        - replace: マージ。キー衝突は後定義（後勝ち）が優先される。

    Attributes:
        rules: overlay ルールのリスト（定義順が合成順序に影響する）。
    """

    rules: list[ScopedOverlayRule] = field(default_factory=list)

    def effective_for(self, image_id: int) -> ExportTagOverlay:
        """image_id に対する実効 overlay を積み上げ合成して返す。

        image_ids=None（グローバル）または image_id が image_ids に含まれる
        ルールのみを合成する。

        Args:
            image_id: 対象画像の DB ID。

        Returns:
            実効 ExportTagOverlay（add dedup 済み、exclude 和集合、replace 後勝ちマージ）。
        """
        # 適用対象ルールを定義順で抽出
        applicable = [rule for rule in self.rules if rule.image_ids is None or image_id in rule.image_ids]

        raw_add: list[str] = []
        combined_exclude: set[str] = set()
        combined_replace: dict[str, str] = {}

        for rule in applicable:
            raw_add.extend(rule.overlay.add)
            combined_exclude |= rule.overlay.exclude
            # replace: 後定義（後勝ち）で上書き
            combined_replace.update(rule.overlay.replace)

        # add の dedup（定義順保持、初出優先）
        seen_add: set[str] = set()
        combined_add: list[str] = []
        for trigger in raw_add:
            if trigger not in seen_add:
                seen_add.add(trigger)
                combined_add.append(trigger)

        return ExportTagOverlay(
            add=combined_add,
            exclude=combined_exclude,
            replace=combined_replace,
        )


def apply_overlay(
    tags: list[str],
    overlay: ExportTagOverlay,
    reader: MergedTagReader | None,
    tag_format: str,
) -> list[str]:
    """per-image タグリストに overlay パイプラインを適用する。

    ADR 0080 §2 のパイプライン順序を実装する純関数:
        1. replace 適用（X→Y）
        2. exclude 除去
        3. convert（alias→preferred + meta 除外。reader=None なら素通し）
        4. add を先頭に literal prepend（convert バイパス）
        5. 順序保持 dedup（先頭=trigger 側を優先して残す）

    不変条件（ADR 0080 §2）:
    - trigger はリテラル: add は convert を通らない。
    - exclude タグは出力に出ない: replace 産 Y も exclude 指定なら消える。
    - dedup 先頭優先: trigger と本文が重複したら trigger（先頭）を残す。
    - reader=None graceful degradation: convert スキップでも replace/exclude/add は機能。

    Args:
        tags: convert 前の採用タグリスト（_resolve_export_tags 済みの文字列リスト）。
        overlay: 適用する ExportTagOverlay（effective_for で合成済みのもの）。
        reader: convert に用いる MergedTagReader。None の場合は convert スキップ。
        tag_format: convert の target format 名（例: "danbooru"）。

    Returns:
        overlay パイプライン適用後のタグリスト。
    """
    # Step 1: replace（X→Y、convert 前に適用）
    after_replace = [overlay.replace.get(tag, tag) for tag in tags]
    # replace が実際に発生したか（いずれかのタグが変化したか）を記録する
    replace_occurred = after_replace != tags

    # Step 2: exclude（convert 前に除去）
    after_exclude = [tag for tag in after_replace if tag not in overlay.exclude]

    # Step 3: convert（alias→preferred + meta 除外、reader=None なら素通し）
    after_convert = _convert_tag_list(after_exclude, tag_format, reader)

    # Step 4: add を先頭に literal prepend（convert バイパス）
    result = list(overlay.add) + after_convert

    # Step 5: 順序保持 dedup（重複を新たに生み得る操作が実際に行われた場合のみ実行）
    # 重複を作り得る操作: add（trigger prepend）と replace（X→Y で新たな重複産生）。
    # exclude は除去のみ、replace.replace が対象画像に一致しない場合（no-op replace）も
    # 重複を生まない。よって add が空かつ実際の replace も発生しなかった場合は
    # dedup をスキップし convert_tags が生む重複多重度をそのまま保持する。
    # これにより overlay_plan=None のレガシー出力と bit 単位で同一になる。
    if not overlay.add and not replace_occurred:
        return result

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in result:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)

    return deduped


def _convert_tag_list(
    tags: list[str],
    tag_format: str,
    reader: MergedTagReader | None,
) -> list[str]:
    """タグリストを convert_tags に通してリストで返す内部ヘルパー。

    空リストまたは reader=None の場合は変換せずそのまま返す
    （graceful degradation、ADR 0080 §2）。

    Args:
        tags: 変換対象タグリスト。
        tag_format: 変換先フォーマット名。
        reader: MergedTagReader。None の場合は変換しない。

    Returns:
        変換後タグリスト。
    """
    if not tags or reader is None:
        return tags

    tags_str = ", ".join(tags)
    converted_str = str(convert_tags(reader, tags_str, tag_format, exclude_types=["meta"]))
    # カンマ区切りをリストに戻す（空要素は除外）
    return [t.strip() for t in converted_str.split(",") if t.strip()]
