"""OpenAI Batch API JSONL結果の一括インポートサービス。

JSONLファイル読み込み → contentパース → custom_id照合 → DB保存の
オーケストレーションを行う。Qt-freeのため、CLI/APIから直接利用可能。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from lorairo.database.db_repository import (
    AnnotationsDict,
    CaptionAnnotationData,
    ImageRepository,
    TagAnnotationData,
)
from lorairo.services.batch_content_parser import BatchContentParser, ParsedAnnotationContent
from lorairo.services.batch_image_matcher import BatchImageMatcher
from lorairo.utils.log import logger


@dataclass(frozen=True)
class BatchImportResult:
    """バッチインポート結果。

    Attributes:
        total_records: JSONL内の総レコード数。
        parsed_ok: パース成功数。
        parse_errors: パースエラー数。
        matched: DB照合成功数。
        unmatched: DB照合失敗数。
        saved: DB保存成功数。
        save_errors: DB保存エラー数。
        model_name: 使用されたモデル名。
        unmatched_ids: マッチ失敗のcustom_idリスト。
        error_details: エラー詳細メッセージリスト。
    """

    total_records: int = 0
    parsed_ok: int = 0
    parse_errors: int = 0
    matched: int = 0
    unmatched: int = 0
    saved: int = 0
    save_errors: int = 0
    model_name: str = ""
    unmatched_ids: list[str] = field(default_factory=list)
    error_details: list[str] = field(default_factory=list)


class BatchImportService:
    """OpenAI Batch API JSONL結果をDBにインポートするサービス（Qt-free）。"""

    def __init__(self, repository: ImageRepository) -> None:
        self._repository = repository
        self._parser = BatchContentParser()
        self._matcher = BatchImageMatcher(repository)

    def import_from_directory(
        self,
        jsonl_dir: Path,
        *,
        dry_run: bool = False,
        model_name_override: str | None = None,
    ) -> BatchImportResult:
        """ディレクトリ内の全JSONLファイルをインポートする。

        Args:
            jsonl_dir: JSONLファイルが格納されたディレクトリ。
            dry_run: Trueの場合、DB書き込みを行わず照合結果のみ返す。
            model_name_override: モデル名を上書きする場合に指定。

        Returns:
            全ファイルの合算インポート結果。

        Raises:
            FileNotFoundError: ディレクトリが存在しない場合。
            ValueError: JSONLファイルが見つからない場合。
        """
        if not jsonl_dir.exists():
            raise FileNotFoundError(f"ディレクトリが見つかりません: {jsonl_dir}")

        jsonl_files = sorted(jsonl_dir.glob("*.jsonl"))
        if not jsonl_files:
            raise ValueError(f"JSONLファイルが見つかりません: {jsonl_dir}")

        logger.info(f"バッチインポート開始: {len(jsonl_files)}ファイル ({jsonl_dir})")

        # 全ファイルの結果を集約
        total_records = 0
        parsed_ok = 0
        parse_errors = 0
        matched = 0
        unmatched = 0
        saved = 0
        save_errors = 0
        model_name = ""
        all_unmatched_ids: list[str] = []
        all_error_details: list[str] = []

        for jsonl_path in jsonl_files:
            result = self.import_from_jsonl(
                jsonl_path, dry_run=dry_run, model_name_override=model_name_override
            )
            total_records += result.total_records
            parsed_ok += result.parsed_ok
            parse_errors += result.parse_errors
            matched += result.matched
            unmatched += result.unmatched
            saved += result.saved
            save_errors += result.save_errors
            if result.model_name and not model_name:
                model_name = result.model_name
            all_unmatched_ids.extend(result.unmatched_ids)
            all_error_details.extend(result.error_details)

        final_result = BatchImportResult(
            total_records=total_records,
            parsed_ok=parsed_ok,
            parse_errors=parse_errors,
            matched=matched,
            unmatched=unmatched,
            saved=saved,
            save_errors=save_errors,
            model_name=model_name_override or model_name,
            unmatched_ids=all_unmatched_ids,
            error_details=all_error_details,
        )

        logger.info(
            f"バッチインポート完了: 合計={total_records}, パース成功={parsed_ok}, "
            f"照合成功={matched}, 保存={saved}"
        )

        return final_result

    def import_from_jsonl(
        self,
        jsonl_path: Path,
        *,
        dry_run: bool = False,
        model_name_override: str | None = None,
    ) -> BatchImportResult:
        """単一JSONLファイルをインポートする。

        Args:
            jsonl_path: JSONLファイルパス。
            dry_run: Trueの場合、DB書き込みを行わず照合結果のみ返す。
            model_name_override: モデル名を上書きする場合に指定。

        Returns:
            インポート結果。
        """
        error_details: list[str] = []

        # 1. JSONLパース
        raw_results, detected_model = self._parse_jsonl_file(jsonl_path)
        total_records = len(raw_results)
        model_name = model_name_override or detected_model or "unknown"

        logger.info(f"JSONL読み込み完了: {jsonl_path.name} ({total_records}件, model={model_name})")

        # 2. contentパース
        parsed: dict[str, ParsedAnnotationContent] = {}
        parse_errors = 0
        for custom_id, content in raw_results.items():
            try:
                parsed[custom_id] = BatchContentParser.parse(content)
            except ValueError as e:
                parse_errors += 1
                error_details.append(f"パースエラー [{custom_id}]: {e}")
                logger.debug(f"パースエラー [{custom_id}]: {e}")

        # 3. custom_id → image_id マッチング
        match_result = self._matcher.match_all(list(parsed.keys()))

        if dry_run:
            return BatchImportResult(
                total_records=total_records,
                parsed_ok=len(parsed),
                parse_errors=parse_errors,
                matched=len(match_result.matched),
                unmatched=len(match_result.unmatched),
                saved=0,
                save_errors=0,
                model_name=model_name,
                unmatched_ids=match_result.unmatched,
                error_details=error_details,
            )

        # 4. モデル解決（get_model_by_name → 未登録なら insert_model）
        model_id = self._resolve_model_id(model_name)

        # 5. タグID一括解決（N+1回避）
        all_tags: set[str] = set()
        for parsed_content in parsed.values():
            for tag in parsed_content.tags:
                all_tags.add(tag.strip().lower())

        tag_id_cache = self._repository.batch_resolve_tag_ids(all_tags)

        # 6. DB保存
        saved = 0
        save_errors = 0
        for custom_id, image_id in match_result.matched.items():
            parsed_content = parsed[custom_id]
            try:
                annotations = self._build_annotations(parsed_content, model_id)
                self._repository.save_annotations(
                    image_id,
                    annotations,
                    skip_existence_check=True,
                    tag_id_cache=tag_id_cache,
                )
                saved += 1
            except Exception as e:
                save_errors += 1
                error_details.append(f"保存エラー [{custom_id}] image_id={image_id}: {e}")
                logger.debug(f"保存エラー [{custom_id}]: {e}")

        logger.info(
            f"JSONL処理完了: {jsonl_path.name} - "
            f"パース={len(parsed)}/{total_records}, "
            f"照合={len(match_result.matched)}, 保存={saved}"
        )

        return BatchImportResult(
            total_records=total_records,
            parsed_ok=len(parsed),
            parse_errors=parse_errors,
            matched=len(match_result.matched),
            unmatched=len(match_result.unmatched),
            saved=saved,
            save_errors=save_errors,
            model_name=model_name,
            unmatched_ids=match_result.unmatched,
            error_details=error_details,
        )

    def _parse_jsonl_file(self, jsonl_path: Path) -> tuple[dict[str, str], str | None]:
        """JSONLファイルを読み込み、{custom_id: content} とモデル名を返す。

        Args:
            jsonl_path: JSONLファイルパス。

        Returns:
            (custom_id→content辞書, 検出モデル名)のタプル。
        """
        results: dict[str, str] = {}
        model_name: str | None = None

        with open(jsonl_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as e:
                    logger.debug(f"JSONパースエラー ({jsonl_path.name}:{line_num}): {e}")
                    continue

                # エラーレスポンスをスキップ
                if data.get("error"):
                    continue

                custom_id = data.get("custom_id")
                response = data.get("response")
                if not custom_id or not response:
                    continue

                if response.get("status_code") != 200:
                    continue

                body = response.get("body", {})
                choices = body.get("choices", [])
                if not choices:
                    continue

                content = choices[0].get("message", {}).get("content")
                if content:
                    results[custom_id] = content

                if model_name is None:
                    model_name = body.get("model")

        return results, model_name

    def _resolve_model_id(self, model_name: str) -> int:
        """モデル名からmodel_idを解決する。未登録なら自動登録する。

        Args:
            model_name: モデル名。

        Returns:
            モデルID。
        """
        existing = self._repository.get_model_by_name(model_name)
        if existing:
            return existing.id

        # 自動登録
        logger.info(f"モデル '{model_name}' を自動登録します")
        return self._repository.insert_model(
            name=model_name,
            provider="openai",
            model_types=["multimodal", "caption", "tags"],
            api_model_id=model_name,
            requires_api_key=True,
        )

    @staticmethod
    def _build_annotations(content: ParsedAnnotationContent, model_id: int) -> AnnotationsDict:
        """ParsedAnnotationContentからAnnotationsDictを構築する。

        Args:
            content: パース済みアノテーション内容。
            model_id: モデルID。

        Returns:
            save_annotations()に渡すAnnotationsDict。
        """
        tags: list[TagAnnotationData] = [
            TagAnnotationData(
                tag=tag.strip(),
                model_id=model_id,
                confidence_score=None,
                existing=False,
                is_edited_manually=False,
                tag_id=None,
            )
            for tag in content.tags
        ]

        captions: list[CaptionAnnotationData] = []
        if content.caption:
            captions.append(
                CaptionAnnotationData(
                    caption=content.caption,
                    model_id=model_id,
                    existing=False,
                    is_edited_manually=False,
                )
            )

        return AnnotationsDict(
            tags=tags,
            captions=captions,
            scores=[],
            ratings=[],
        )
