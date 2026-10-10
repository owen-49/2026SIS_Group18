"""Acceptance harness regressions; no model downloads or paid provider calls."""

import argparse
import json
from types import SimpleNamespace

import httpx
import pytest
from backend.scripts import acceptance_citation_comparison as acceptance
from backend.src import user_ai
from backend.src.services import citation_comparison_service
from backend.src.services.user_ai_runtime import UserAIError, UserAIRuntime
from backend.src.storage import bib_document_store, paper_store, parsed_document_store


def report_for(provider="openai", *, limit=3, cases=None):
    return acceptance.make_report(
        argparse.Namespace(
            provider=provider,
            model="account-model",
            region=None,
            workspace=None,
            case=cases,
            live=True,
            max_calls=limit,
        )
    )


def comparison_body(verdict="SUPPORT", **updates):
    body = {
        "claim": acceptance.CASES[0].claim,
        "citation_marker": r"\cite{vaswani2017attention}",
        "status": "COMPARED",
        "message": "Compared.",
        "source_paper_id": "src-transformer",
        "judgement": {"verdict": verdict, "confidence": 0.9, "rationale": "private-rationale"},
        "evidence": [{"passage_text": "Source text.", "page": 1, "rank": 1, "similarity": 0.9}],
    }
    body.update(updates)
    return body


@pytest.mark.parametrize("case", acceptance.CASES)
def test_actual_expected_verdict_matches(case):
    result = acceptance.evaluate(
        case,
        httpx.Response(
            200,
            json=comparison_body(
                case.expected_verdict,
            ),
        ),
    )
    assert result["outcome"] == "passed"
    assert result["actual"]["verdict"] == case.expected_verdict


def test_wrong_verdict_is_failed_not_success(tmp_path):
    report = report_for(cases=["support"])
    row = next(row for row in report["cases"] if row["selected"])
    row.update(
        acceptance.evaluate(
            acceptance.CASES[0],
            httpx.Response(
                200,
                json=comparison_body("CONTRADICT"),
            ),
        )
    )
    assert row["reason"] == "verdict_mismatch"
    assert acceptance.write_report(report, tmp_path / "report.json") == 1
    assert report["selected_summary"] == {"passed": 0, "failed": 1, "untested": 0}


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"status": "LLM_FAILED", "judgement": None}, "comparison_incomplete"),
        ({"evidence": []}, "missing_evidence"),
        (
            {"evidence": [{"passage_text": " ", "page": 1, "rank": 1, "similarity": 0.9}]},
            "missing_evidence",
        ),
        ({"source_paper_id": "wrong-source"}, "wrong_source"),
        (
            {"judgement": {"verdict": "UNKNOWN", "confidence": 0.9, "rationale": "bad"}},
            "invalid_response",
        ),
        (
            {"evidence": [{"passage_text": "text", "page": 0, "rank": 1, "similarity": 0.9}]},
            "invalid_response",
        ),
    ],
)
def test_incomplete_or_invalid_comparison_is_failed(updates, reason):
    result = acceptance.evaluate(
        acceptance.CASES[0],
        httpx.Response(
            200,
            json=comparison_body(**updates),
        ),
    )
    assert result["outcome"] == "failed"
    assert result["reason"] == reason


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="private-non-json-body"),
        httpx.Response(200, json=["private-body"]),
        httpx.Response(502, json={"detail": {"code": "private-code", "message": "secret-key"}}),
        httpx.Response(401, json={"detail": {"code": "AI_AUTH_FAILED", "message": "secret-key"}}),
    ],
)
def test_reports_do_not_copy_private_response_content(response):
    result = acceptance.evaluate(acceptance.CASES[0], response)
    encoded = json.dumps(result)
    assert result["outcome"] == "failed"
    assert "private-" not in encoded and "secret-key" not in encoded


def test_plan_never_prompts_or_runs_live_and_returns_incomplete(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Planning must not enter the live path")

    monkeypatch.setattr(acceptance.getpass, "getpass", unexpected)
    monkeypatch.setattr(acceptance, "run_live", unexpected)
    target = tmp_path / "plan.json"
    assert acceptance.main(["--report", str(target)]) == 2
    report = json.loads(target.read_text())
    assert report["summary"] == {
        "passed": 0,
        "failed": 0,
        "untested": len(acceptance.available_providers()) * 3,
    }
    assert report["mode"] == "plan"
    assert report["budget"]["calls_attempted"] == 0


@pytest.mark.parametrize("extra", [[], ["--max-calls", "0"], ["--max-calls", "-1"]])
def test_live_requires_explicit_positive_budget(extra):
    with pytest.raises(SystemExit) as error:
        acceptance.main(["--live", "--provider", "openai", "--model", "m", *extra])
    assert error.value.code == 2


def test_live_without_interactive_credentials_is_untested(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance.sys.stdin, "isatty", lambda: False)
    target = tmp_path / "report.json"
    assert (
        acceptance.main(
            [
                "--live",
                "--provider",
                "openai",
                "--model",
                "m",
                "--max-calls",
                "1",
                "--report",
                str(target),
            ]
        )
        == 2
    )
    report = json.loads(target.read_text())
    assert report["selected_summary"] == {"passed": 0, "failed": 0, "untested": 3}
    assert report["budget"]["calls_attempted"] == 0


@pytest.fixture()
def offline_wire(monkeypatch):
    """Keep real API/Engine/SDK conversion, fake retrieval and HTTP transport."""

    class Retriever:
        def build_index(self, passages):
            self.passages = passages

        def retrieve(self, claim, k=5):
            return [
                SimpleNamespace(
                    passage=passage,
                    passage_index=index,
                    rank=index + 1,
                    score=0.9,
                )
                for index, passage in enumerate(self.passages[:k])
            ]

    calls = []
    replies = []

    def respond(request):
        calls.append(request)
        reply = replies.pop(0)
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"label": reply, "rationale": "ok"}),
                        },
                    }
                ],
            },
        )

    original = user_ai.OpenAI
    monkeypatch.setattr(
        user_ai,
        "OpenAI",
        lambda **kw: original(
            **kw,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        ),
    )
    monkeypatch.setattr(citation_comparison_service, "_new_retriever", Retriever)
    return calls, replies


def test_full_offline_chain_checks_all_verdicts_and_restores_stores(
    offline_wire,
    tmp_path,
    monkeypatch,
):
    calls, replies = offline_wire
    replies.extend(case.expected_verdict for case in acceptance.CASES)
    original_paths = (
        paper_store.PAPERS_FILE,
        parsed_document_store.PARSED_DIR,
        bib_document_store.BIB_PARSED_DIR,
    )
    # Exercise the CLI, hidden prompt, isolated store, real route and SDK boundary.
    monkeypatch.setattr(acceptance.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(acceptance.getpass, "getpass", lambda prompt: "offline-secret")
    target = tmp_path / "report.json"
    assert (
        acceptance.main(
            [
                "--live",
                "--provider",
                "openai",
                "--model",
                "account-model",
                "--max-calls",
                "3",
                "--report",
                str(target),
            ]
        )
        == 0
    )
    report = json.loads(target.read_text())
    assert report["selected_summary"] == {"passed": 3, "failed": 0, "untested": 0}
    assert report["summary"]["untested"] == (len(acceptance.available_providers()) - 1) * 3
    assert len(calls) == report["budget"]["calls_attempted"] == 3
    assert "offline-secret" not in target.read_text()
    assert original_paths == (
        paper_store.PAPERS_FILE,
        parsed_document_store.PARSED_DIR,
        bib_document_store.BIB_PARSED_DIR,
    )


def test_budget_skips_remaining_cases_instead_of_marking_passed(offline_wire, tmp_path):
    calls, replies = offline_wire
    replies.append("SUPPORT")
    report = report_for(limit=1)
    budget = acceptance.CallBudget(1)
    with acceptance.scratch_library():
        acceptance.run_live(
            report,
            {
                "provider": "openai",
                "model": "m",
                "api_key": "offline-secret",
            },
            budget,
        )
    report["budget"]["calls_attempted"] = budget.attempted
    assert acceptance.write_report(report, tmp_path / "report.json") == 2
    assert report["selected_summary"] == {"passed": 1, "failed": 0, "untested": 2}
    assert len(calls) == budget.attempted == 1
    assert all(
        row["reason"] == "budget_exhausted"
        for row in report["cases"]
        if row["selected"] and row["outcome"] == "untested"
    )


def test_auth_failure_stops_remaining_cases_and_redacts_error(offline_wire, tmp_path):
    calls, replies = offline_wire
    replies.append(httpx.Response(401, json={"error": {"message": "offline-secret private-body"}}))
    report = report_for()
    budget = acceptance.CallBudget(3)
    with acceptance.scratch_library():
        acceptance.run_live(
            report,
            {
                "provider": "openai",
                "model": "m",
                "api_key": "offline-secret",
            },
            budget,
        )
    assert acceptance.write_report(report, tmp_path / "report.json") == 1
    assert report["selected_summary"] == {"passed": 0, "failed": 1, "untested": 2}
    assert len(calls) == budget.attempted == 1
    assert "offline-secret" not in json.dumps(report) and "private-body" not in json.dumps(report)


def test_runtime_guard_bounds_extra_ai_calls():
    calls = []
    raw = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: calls.append(kwargs),
            )
        )
    )
    runtime = UserAIRuntime(raw, "m")
    budget = acceptance.CallBudget(1)
    with acceptance.enforce_budget(budget):
        runtime.create(messages=[])
        with pytest.raises(UserAIError, match="budget"):
            runtime.create(messages=[])
        with pytest.raises(UserAIError, match="budget"):
            runtime.create(messages=[])
    assert len(calls) == budget.attempted == 1


def test_failed_case_does_not_hide_later_results(offline_wire, tmp_path):
    calls, replies = offline_wire
    replies.extend(["CONTRADICT", "CONTRADICT", "NOT_FOUND"])
    report = report_for()
    budget = acceptance.CallBudget(3)
    with acceptance.scratch_library():
        acceptance.run_live(
            report,
            {
                "provider": "openai",
                "model": "m",
                "api_key": "offline-secret",
            },
            budget,
        )
    assert acceptance.write_report(report, tmp_path / "report.json") == 1
    assert report["selected_summary"] == {"passed": 2, "failed": 1, "untested": 0}
    assert len(calls) == 3


def test_invalid_region_is_untested_without_prompt_or_call(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid configuration must not prompt or call a provider")

    monkeypatch.setattr(acceptance.getpass, "getpass", unexpected)
    monkeypatch.setattr(acceptance, "run_live", unexpected)
    target = tmp_path / "report.json"
    assert (
        acceptance.main(
            [
                "--live",
                "--provider",
                "openai",
                "--model",
                "m",
                "--region",
                "invalid-region",
                "--max-calls",
                "1",
                "--report",
                str(target),
            ]
        )
        == 2
    )
    report = json.loads(target.read_text())
    assert report["budget"]["calls_attempted"] == 0
    assert report["selected_summary"] == {"passed": 0, "failed": 0, "untested": 3}


@pytest.mark.skipif(
    "qwen" not in acceptance.available_providers(),
    reason="Requires the provider expansion in PR #60",
)
def test_qwen_region_workspace_and_selected_case_reach_actual_route(
    offline_wire,
    tmp_path,
    monkeypatch,
):
    calls, replies = offline_wire
    replies.append("SUPPORT")
    monkeypatch.setattr(acceptance.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(acceptance.getpass, "getpass", lambda prompt: "offline-secret")
    target = tmp_path / "qwen.json"
    assert (
        acceptance.main(
            [
                "--live",
                "--provider",
                "qwen",
                "--model",
                "qwen3-plus",
                "--region",
                "singapore",
                "--workspace",
                "workspace123",
                "--case",
                "support",
                "--max-calls",
                "1",
                "--report",
                str(target),
            ]
        )
        == 0
    )
    report = json.loads(target.read_text())
    assert report["selected_summary"] == {"passed": 1, "failed": 0, "untested": 0}
    assert report["summary"]["untested"] == len(acceptance.available_providers()) * 3 - 1
    assert str(calls[0].url) == (
        "https://workspace123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert json.loads(calls[0].content)["enable_thinking"] is False
    assert report["configuration"]["workspace"] == "workspace123"


@pytest.mark.skipif(
    "anthropic" not in acceptance.available_providers(),
    reason="Requires the provider expansion in PR #60",
)
def test_native_claude_acceptance_is_counted_and_checked(offline_wire, monkeypatch):
    original_http = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": '{"label":"SUPPORT","rationale":"ok"}'}],
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_http(
            **kwargs,
            transport=httpx.MockTransport(respond),
        ),
    )
    report = report_for("anthropic", limit=1, cases=["support"])
    budget = acceptance.CallBudget(1)
    with acceptance.scratch_library():
        acceptance.run_live(
            report,
            {
                "provider": "anthropic",
                "model": "account-model",
                "api_key": "offline-secret",
            },
            budget,
        )
    selected = [row for row in report["cases"] if row["selected"]]
    assert selected[0]["outcome"] == "passed"
    assert selected[0]["actual"]["verdict"] == "SUPPORT"
    assert len(calls) == budget.attempted == 1
    assert calls[0].url.path == "/v1/messages"
