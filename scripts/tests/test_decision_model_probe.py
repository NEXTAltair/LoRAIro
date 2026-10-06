"""Protocol, leakage and measurement checks without external requests."""

import argparse
import importlib.util
import json
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "decision_probe", Path(__file__).parents[1] / "probe_decision_models.py"
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def args(**overrides):
    values = {"provider": "typesafe", "model": "jev-latest", "live": True, "timeout": 1, "attempts": 1}
    return argparse.Namespace(**(values | overrides))


def caption_case():
    return {
        "id": "caption",
        "task": "caption_check",
        "caption": "Her eyes is blue.",
        "expected": {"grammar_error": True},
    }


def preference_case():
    return {
        "id": "target",
        "task": "preference",
        "description": "A quiet forest.",
        "manual_score": 8.123,
        "examples": [{"id": "past", "description": "A quiet lake.", "manual_score": 9.5}],
    }


def response_for(payload):
    answers = {}
    for key, question in payload["questions"].items():
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 0.9}
        else:
            answers[key] = {
                "type": "score",
                "score": 3.6,
                "confidence": 0.8,
                "probabilities": {"0": 0, "1": 0, "2": 0, "3": 0.4, "4": 0.6},
            }
    return {"model": "actual-model-version", "answers": answers, "usage": {"input_tokens": 50}}


def test_preference_holdout_is_not_sent_and_baseline_drops_history(tmp_path):
    case = probe.build_case(preference_case(), tmp_path)
    with_history = probe.request_chunks(case, "jev", False)[0]
    without = probe.request_chunks(case, "jev", True)[0]
    assert "8.123" not in json.dumps(with_history)
    assert "9.5" in json.dumps(with_history)
    assert "rated_examples" not in without["state"]
    assert case["expected"] == {"preference": 8.123}


def test_preference_uses_manual_scale_and_keeps_both_variants(tmp_path):
    case = probe.build_case(preference_case(), tmp_path)
    sender = Mock(side_effect=lambda _url, _key, payload, *_args: response_for(payload))
    reports = probe.evaluate_case(case, args(), "secret-token", "https://example.test", sender)
    assert sender.call_count == 2
    assert {report["variant"] for report in reports} == {"with_history", "without_history"}
    assert reports[0]["labels"][0]["predicted"] == 9.0
    assert reports[0]["labels"][0]["absolute_error"] == pytest.approx(0.877)
    assert "secret-token" not in json.dumps(reports)
    assert reports[0]["models"] == ["actual-model-version"]


def test_unrated_target_has_no_zero_label(tmp_path):
    source = preference_case()
    del source["manual_score"]
    case = probe.build_case(source, tmp_path)
    assert case["expected"] == {}


def test_unlabeled_quality_still_reports_score_on_manual_scale(tmp_path):
    case = probe.build_case(
        {"id": "quality", "task": "quality_score", "description": "A sharp image."}, tmp_path
    )
    sender = Mock(side_effect=lambda _url, _key, payload, *_args: response_for(payload))
    reports = probe.evaluate_case(case, args(), "secret", "https://example.test", sender)
    assert reports[0]["scores_0_to_10"] == {"quality": 9.0}
    assert reports[0]["labels"] == []


def test_custom_choice_keeps_state_and_expected_separate(tmp_path):
    source = {
        "id": "custom",
        "task": "custom",
        "state": {"purpose": "sleeve detail"},
        "questions": {
            "crop": {
                "type": "choice",
                "instructions": "Which crop preserves detail?",
                "criteria": {"a": "wider", "b": "tighter"},
            }
        },
        "expected": {"crop": "b"},
    }
    case = probe.build_case(source, tmp_path)
    payload = probe.request_chunks(case, "clef", False)[0]
    assert "expected" not in payload
    response = {
        "model": "clef",
        "answers": {
            "crop": {
                "type": "choice",
                "choice": "b",
                "confidence": 0.8,
                "probabilities": {"a": 0.1, "b": 0.9},
            }
        },
    }
    reports = probe.evaluate_case(
        case, args(provider="cloudflare"), "secret", "https://example.test", Mock(return_value=response)
    )
    assert reports[0]["labels"][0]["correct"] is True


@pytest.mark.parametrize("label", [float("nan"), float("inf"), -1, 11, True])
def test_bad_manual_scores_rejected(tmp_path, label):
    source = preference_case() | {"manual_score": label}
    with pytest.raises(ValueError):
        probe.build_case(source, tmp_path)


def test_target_in_history_rejected_by_id(tmp_path):
    source = preference_case()
    source["examples"][0]["id"] = "target"
    with pytest.raises(ValueError, match="must not appear"):
        probe.build_case(source, tmp_path)


def test_text_proxy_target_in_history_rejected_even_with_different_id(tmp_path):
    source = preference_case()
    source["examples"][0]["description"] = " A QUIET FOREST. "
    with pytest.raises(ValueError, match="description must not appear"):
        probe.build_case(source, tmp_path)


@pytest.mark.parametrize("state", ["plain text", ["first", "second"]])
def test_custom_string_and_array_states(tmp_path, state):
    source = {
        "id": "custom",
        "task": "custom",
        "state": state,
        "questions": {"test": {"type": "noul", "instructions": "Is this complete?"}},
    }
    assert probe.build_case(source, tmp_path)["state"] == state


def test_malformed_choice_is_a_case_error_not_a_crash(tmp_path):
    source = {
        "id": "custom",
        "task": "custom",
        "state": "test",
        "questions": {
            "test": {
                "type": "choice",
                "instructions": "Choose one.",
                "criteria": {"a": "first", "b": "second"},
            }
        },
    }
    case = probe.build_case(source, tmp_path)
    response = {
        "model": "clef",
        "answers": {
            "test": {
                "type": "choice",
                "choice": [],
                "confidence": 0.5,
                "probabilities": {"a": 0.5, "b": 0.5},
            }
        },
    }
    reports = probe.evaluate_case(
        case, args(provider="cloudflare"), "secret", "https://example.test", Mock(return_value=response)
    )
    assert reports[0]["status"] == "error"


def test_oversized_later_payload_prevents_live_requests(tmp_path, monkeypatch):
    source = tmp_path / "cases.jsonl"
    huge = {
        "id": "too-large",
        "task": "custom",
        "state": "x" * (13 * 1024 * 1024),
        "questions": {"test": {"type": "noul", "instructions": "Is this complete?"}},
    }
    source.write_text(json.dumps(caption_case()) + "\n" + json.dumps(huge))
    credential_loader = Mock()
    monkeypatch.setattr(probe, "credentials", credential_loader)
    assert probe.main(["--cases", str(source), "--live", "--output", str(tmp_path / "results.json")]) == 2
    credential_loader.assert_not_called()


def test_target_image_copy_rejected_and_baseline_keeps_only_target(tmp_path):
    target = tmp_path / "target.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nfixture-target")
    past = tmp_path / "past.png"
    past.write_bytes(target.read_bytes())
    source = preference_case() | {"image": target.name}
    source["examples"][0]["image"] = past.name
    with pytest.raises(ValueError, match="must not appear"):
        probe.build_case(source, tmp_path)
    past.write_bytes(b"\x89PNG\r\n\x1a\nfixture-different")
    case = probe.build_case(source, tmp_path)
    assert len(probe.request_chunks(case, "clef", False)[0]["images"]) == 2
    assert probe.request_chunks(case, "clef", True)[0]["images"] == case["images"][:1]


def test_text_proxy_target_with_history_images_is_still_text_proxy(tmp_path):
    (tmp_path / "past.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    source = preference_case()
    source["examples"][0]["image"] = "past.png"
    case = probe.build_case(source, tmp_path)
    assert case["basis"] == "text_proxy"
    assert "images" not in probe.request_chunks(case, "clef", True)[0]


def test_jev_image_case_is_skipped_without_sending(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    case = probe.build_case(
        {"id": "image", "task": "tag_fit", "image": "image.png", "tags": ["cat"]}, tmp_path
    )
    sender = Mock()
    reports = probe.evaluate_case(case, args(), "secret", "https://example.test", sender)
    sender.assert_not_called()
    assert reports[0]["status"] == "skipped"
    assert reports[0]["basis"] == "image"


def test_65_tags_split_and_join_cloudflare_wrapped_answers(tmp_path):
    source = {
        "id": "tags",
        "task": "tag_fit",
        "description": "One cat.",
        "tags": [f"tag{n}" for n in range(65)],
        "expected": {"tag_000": True, "tag_064": False},
    }
    case = probe.build_case(source, tmp_path)
    sender = Mock(
        side_effect=lambda _url, _key, payload, *_args: {"success": True, "result": response_for(payload)}
    )
    reports = probe.evaluate_case(
        case, args(provider="cloudflare", model="clef"), "secret", "https://example.test", sender
    )
    assert [len(call.args[2]["questions"]) for call in sender.call_args_list] == [64, 1]
    assert len(reports[0]["answers"]) == 65
    summary = probe.summarize(reports)
    assert summary["metrics"]["tag_fit:text_proxy:default"]["accuracy"] == 0.5
    assert summary["metrics"]["tag_fit:text_proxy:default"]["brier"] == pytest.approx(0.41)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda response: response["answers"].pop("grammar_error"),
        lambda response: response["answers"]["grammar_error"].update(noul=2),
        lambda response: response["answers"]["grammar_error"].update(noul=float("nan")),
        lambda response: response["answers"]["grammar_error"].update(type="choice"),
    ],
)
def test_malformed_response_is_not_counted_as_accuracy(tmp_path, mutation):
    case = probe.build_case(caption_case(), tmp_path)
    response = response_for(probe.request_chunks(case, "jev", False)[0])
    mutation(response)
    reports = probe.evaluate_case(
        case, args(), "secret", "https://example.test", Mock(return_value=response)
    )
    assert reports[0]["status"] == "error"
    assert probe.summarize(reports)["metrics"] == {}


def test_http_retry_and_error_body_are_not_exposed(monkeypatch):
    failed = urllib.error.HTTPError(
        "https://example.test", 429, "secret message", {"Retry-After": "1"}, None
    )
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"answers": {}}'
    opener = Mock()
    opener.open.side_effect = [failed, response]
    monkeypatch.setattr(probe.urllib.request, "build_opener", lambda *_: opener)
    sleep = Mock()
    monkeypatch.setattr(probe.time, "sleep", sleep)
    assert probe.post_json("https://example.test", "secret", {"state": "test"}, 1, 2) == {"answers": {}}
    sleep.assert_called_once_with(1)
    opener.open.side_effect = urllib.error.HTTPError(
        "https://example.test", 401, "secret message", {}, None
    )
    with pytest.raises(ValueError, match="HTTP 401") as error:
        probe.post_json("https://example.test", "secret", {}, 1, 1)
    assert "secret" not in str(error.value)


def test_dry_run_sample_suite_never_requests_credentials_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "credentials", Mock(side_effect=AssertionError("must not load keys")))
    monkeypatch.setattr(
        probe.urllib.request, "build_opener", Mock(side_effect=AssertionError("must not call API"))
    )
    output = tmp_path / "results.json"
    cases = Path(__file__).parents[1] / "decision_probe_cases.jsonl"
    assert probe.main(["--cases", str(cases), "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["summary"]["statuses"] == {"dry_run": 18}
    assert result["summary"]["metrics"] == {}


def test_output_cannot_overwrite_input(tmp_path):
    source = tmp_path / "cases.jsonl"
    original = json.dumps(caption_case()) + "\n"
    source.write_text(original)
    assert probe.main(["--cases", str(source), "--output", str(source)]) == 2
    assert source.read_text() == original


def test_invalid_later_case_prevents_any_live_requests(tmp_path, monkeypatch):
    source = tmp_path / "cases.jsonl"
    source.write_text(json.dumps(caption_case()) + "\n" + json.dumps({"id": "bad", "task": "preference"}))
    credential_loader = Mock()
    monkeypatch.setattr(probe, "credentials", credential_loader)
    assert probe.main(["--cases", str(source), "--live", "--output", str(tmp_path / "results.json")]) == 2
    credential_loader.assert_not_called()
