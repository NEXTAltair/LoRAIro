"""RefinementService のユニットテスト (#931)。

lib の recommend 関数はモックし、ignore 除外・キャッシュ・needs_refinement
判定のロジックを検証する。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import (
    RefinementReason,
    RefinementRecommendation,
    RefinementSuggestion,
)

from lorairo.services.refinement_service import RefinementService

pytestmark = pytest.mark.unit


def _make_recommendation(
    tag: str,
    *,
    needs: bool = True,
    reason_codes: list[str] | None = None,
    suggestion_tag: str | None = None,
) -> RefinementRecommendation:
    """テスト用 RefinementRecommendation を組み立てる。"""
    reasons = [
        RefinementReason(code=code, message=f"{code} message")  # type: ignore[arg-type]
        for code in (reason_codes or [])
    ]
    suggestions = (
        [RefinementSuggestion(kind="correction_candidate", tag=suggestion_tag)]
        if suggestion_tag is not None
        else []
    )
    return RefinementRecommendation(
        source_tag=tag,
        normalized_tag=tag,
        needs_refinement=needs,
        score=0.8 if needs else 0.0,
        reasons=reasons,
        suggestions=suggestions,
        proposals=[],
    )


class _FakeIgnoreRepo:
    """RefinementIgnoreRepository の振る舞いを模した in-memory fake。"""

    def __init__(self, ignored: set[tuple[str, str]] | None = None) -> None:
        self._ignored: set[tuple[str, str]] = set(ignored or set())

    def add_ignore(self, tag: str, reason_code: str) -> None:
        self._ignored.add((tag, reason_code))

    def is_ignored(self, tag: str, reason_code: str) -> bool:
        return (tag, reason_code) in self._ignored

    def list_ignored(self) -> set[tuple[str, str]]:
        return set(self._ignored)


def test_recommend_for_tags_returns_only_needs_refinement() -> None:
    """needs_refinement=True のタグだけ返す。"""
    recs = {
        "blue__eyes": _make_recommendation(
            "blue__eyes", reason_codes=["normalization_changes_tag"], suggestion_tag="blue_eyes"
        ),
        "blue_eyes": _make_recommendation("blue_eyes", needs=False),
    }

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return recs[tag]

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    result = service.recommend_for_tags(["blue__eyes", "blue_eyes"])

    assert set(result.keys()) == {"blue__eyes"}
    assert result["blue__eyes"].suggestions[0].tag == "blue_eyes"


def test_recommend_for_tags_excludes_ignored_reason_code() -> None:
    """ignore された (tag, reason_code) は reasons から除外される。"""
    rec = _make_recommendation("flower", reason_codes=["broad_single_word", "normalization_changes_tag"])

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return rec

    ignore_repo = _FakeIgnoreRepo({("flower", "broad_single_word")})
    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=ignore_repo)
    result = service.recommend_for_tags(["flower"])

    assert "flower" in result
    codes = {r.code for r in result["flower"].reasons}
    assert codes == {"normalization_changes_tag"}


def test_recommend_for_tags_drops_tag_when_all_reasons_ignored() -> None:
    """全 reason が ignore されたタグは結果から落ちる (needs_refinement=False 扱い)。"""
    rec = _make_recommendation("bad_id", reason_codes=["training_unsuitable"])

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return rec

    ignore_repo = _FakeIgnoreRepo({("bad_id", "training_unsuitable")})
    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=ignore_repo)
    result = service.recommend_for_tags(["bad_id"])

    assert result == {}


def test_recommend_for_tags_caches_repeated_tags() -> None:
    """同一 (tag, format_name) は lib を1回だけ呼ぶ (メモ化)。"""
    calls: list[str] = []

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        calls.append(tag)
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    service.recommend_for_tags(["flower"])
    service.recommend_for_tags(["flower"])

    assert calls == ["flower"]


def test_recommend_for_tags_calls_prefetch_once_with_uncached_tags() -> None:
    """prefetch_fn は per-tag 評価の前に未キャッシュタグ (dedup 済) で 1 回だけ呼ばれる (#998)。"""
    prefetch_calls: list[list[str]] = []
    order: list[str] = []

    def fake_prefetch(tags: object, *, repo: object = None) -> None:
        prefetch_calls.append(list(tags))  # type: ignore[arg-type]
        order.append("prefetch")

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        order.append(f"eval:{tag}")
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(
        recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo(), prefetch_fn=fake_prefetch
    )
    service.recommend_for_tags(["a", "b", "a"])

    # dedup 済み・未キャッシュのみ、1 回だけ
    assert prefetch_calls == [["a", "b"]]
    # prefetch は全 per-tag 評価より前
    assert order[0] == "prefetch"
    assert order.count("prefetch") == 1


def test_recommend_for_tags_prefetch_skips_cached_tags() -> None:
    """2 回目の呼び出しでは既キャッシュタグを prefetch 対象から除く (#998)。"""
    prefetch_calls: list[list[str]] = []

    def fake_prefetch(tags: object, *, repo: object = None) -> None:
        prefetch_calls.append(list(tags))  # type: ignore[arg-type]

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(
        recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo(), prefetch_fn=fake_prefetch
    )
    service.recommend_for_tags(["a", "b"])
    service.recommend_for_tags(["a", "b", "c"])

    assert prefetch_calls == [["a", "b"], ["c"]]


def test_recommend_for_tags_without_prefetch_fn_still_works() -> None:
    """prefetch_fn 未注入でも従来どおり評価できる (後方互換、#998)。"""

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    result = service.recommend_for_tags(["flower"])

    assert "flower" in result


def test_recommend_for_tags_uses_format_map() -> None:
    """format_map の値が recommend_fn の format_name に渡る。"""
    seen: dict[str, str] = {}

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        seen[tag] = format_name
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    service.recommend_for_tags(["flower"], format_map={"flower": "danbooru"})

    assert seen["flower"] == "danbooru"


def test_partial_ignore_drops_suggestions() -> None:
    """一部 reason を ignore したら suggestions も落とす (ignored reason の修正漏れ防止、Codex P2)。"""
    rec = _make_recommendation(
        "flower",
        reason_codes=["broad_single_word", "normalization_changes_tag"],
        suggestion_tag="rose",
    )

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return rec

    ignore_repo = _FakeIgnoreRepo({("flower", "normalization_changes_tag")})
    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=ignore_repo)
    result = service.recommend_for_tags(["flower"])

    assert {r.code for r in result["flower"].reasons} == {"broad_single_word"}
    assert result["flower"].suggestions == []


def test_clear_cache_forces_reevaluation() -> None:
    """clear_cache() 後は再評価する (tagdb 編集後の stale 解消、Codex P2)。"""
    calls: list[str] = []

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        calls.append(tag)
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    service.recommend_for_tags(["flower"])
    service.clear_cache()
    service.recommend_for_tags(["flower"])

    assert calls == ["flower", "flower"]  # clear 後に再評価


def test_different_repo_bypasses_cache() -> None:
    """reader (repo) が違えば別キーとして再評価する (Codex P2)。"""
    calls: list[object] = []

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        calls.append(repo)
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    reader_a = object()
    reader_b = object()
    service.recommend_for_tags(["flower"], repo=reader_a)
    service.recommend_for_tags(["flower"], repo=reader_b)

    assert calls == [reader_a, reader_b]  # reader 違いで2回評価


class _CancelRequested(Exception):
    """テスト用の中断シグナル例外 (cancel_check が送出する)。"""


def test_cancel_check_called_before_prefetch_and_each_evaluation() -> None:
    """cancel_check は prefetch 前と per-tag 評価 (DB 往復) の直前に呼ばれる (#1024)。"""
    order: list[str] = []

    def fake_prefetch(tags: object, *, repo: object = None) -> None:
        order.append("prefetch")

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        order.append(f"eval:{tag}")
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    def cancel_check() -> None:
        order.append("check")

    service = RefinementService(
        recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo(), prefetch_fn=fake_prefetch
    )
    service.recommend_for_tags(["a", "b"], cancel_check=cancel_check)

    # 先頭の check は list_ignored() (これも DB 読み取り) の前のチェックポイント (Codex P2)
    assert order == ["check", "check", "prefetch", "check", "eval:a", "check", "eval:b"]


def test_cancel_check_aborts_between_evaluations() -> None:
    """途中でキャンセル要求が入ると残りの評価を行わず例外が伝播する (#1024)。"""
    calls: list[str] = []
    checks = 0

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        calls.append(tag)
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    def cancel_check() -> None:
        nonlocal checks
        checks += 1
        if checks > 2:  # 先頭 (list_ignored 前) + 1タグ目の直前を通過後にキャンセルされた想定
            raise _CancelRequested()

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    with pytest.raises(_CancelRequested):
        service.recommend_for_tags(["a", "b", "c"], cancel_check=cancel_check)

    assert calls == ["a"]  # 2タグ目以降は評価しない


def test_cached_tags_skip_per_tag_cancel_checks() -> None:
    """全タグがキャッシュ済みなら per-tag のチェックは走らない (先頭の1回のみ)。

    先頭の1回は list_ignored() (毎回の DB 読み取り) の前のチェックポイントで、
    キャッシュ状態に依らず常に走る (Codex P2)。
    """
    checks = 0

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    def counting_check() -> None:
        nonlocal checks
        checks += 1

    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=_FakeIgnoreRepo())
    service.recommend_for_tags(["flower"])  # キャッシュ投入

    result = service.recommend_for_tags(["flower"], cancel_check=counting_check)
    assert "flower" in result
    assert checks == 1  # per-tag 評価分のチェックは走らない


def test_ignore_persists_and_invalidates_cache() -> None:
    """ignore 後はそのタグの該当 reason が以後の結果から消える (キャッシュ無効化)。"""

    def fake_recommend(tag: str, *, repo: object = None, format_name: str = "unknown"):
        return _make_recommendation(tag, reason_codes=["broad_single_word"])

    ignore_repo = _FakeIgnoreRepo()
    service = RefinementService(recommend_fn=fake_recommend, ignore_repo=ignore_repo)

    first = service.recommend_for_tags(["flower"])
    assert "flower" in first

    service.ignore("flower", "broad_single_word")
    second = service.recommend_for_tags(["flower"])
    assert second == {}
    assert ignore_repo.is_ignored("flower", "broad_single_word")
