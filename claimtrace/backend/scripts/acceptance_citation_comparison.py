"""Budgeted Verify acceptance with actual/expected checks and a JSON report.

Default mode only writes an untested matrix. Live execution requires --live,
an explicit --max-calls budget, and a key entered at a hidden terminal prompt.
Live runs use real embeddings/retrieval but seed parsed fixtures: PDF parsing
is outside this suite. See docs/verify-acceptance.md for scope and exit codes.
"""

import argparse
import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import get_args
from unittest.mock import patch

# backend/ is not installed as a package, so make the repository root importable
# no matter which directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SOURCE_TITLE = "Attention Is All You Need"

# A faithful excerpt of the cited paper's own wording.
SOURCE_PARAGRAPHS = [
    "We propose a new simple network architecture, the Transformer, based solely "
    "on attention mechanisms, dispensing with recurrence and convolutions entirely.",
    "We call our particular attention “Scaled Dot-Product Attention”. "
    "The input consists of queries and keys of dimension dk, and values of "
    "dimension dv.",
    "Self-attention, sometimes called intra-attention, is an attention mechanism "
    "relating different positions of a single sequence in order to compute a "
    "representation of the sequence. Self-attention has been used successfully in "
    "a variety of tasks including reading comprehension and summarization.",
    "The Transformer follows this overall architecture using stacked self-attention "
    "and point-wise, fully connected layers for both the encoder and decoder.",
    "We trained the base model for 100,000 steps or 12 hours on 8 NVIDIA P100 GPUs.",
]


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    expected_verdict: str
    claim: str


CASES = (
    AcceptanceCase(
        "support",
        "SUPPORT",
        "Self-attention is an attention mechanism that relates different positions of a "
        "single sequence in order to compute a representation of that sequence.",
    ),
    AcceptanceCase(
        "contradict",
        "CONTRADICT",
        "The paper's self-attention mechanism depends on recurrence to relate different "
        "positions of a single sequence.",
    ),
    AcceptanceCase(
        "not_found",
        "NOT_FOUND",
        "The paper reports that the method reduced carbon emissions by forty percent.",
    ),
    AcceptanceCase(
        "partial_tasks",
        "PARTIAL",
        "Self-attention relates positions within a single sequence and has been "
        "demonstrated to work successfully on every possible task.",
    ),
    AcceptanceCase(
        "causal_not_found",
        "NOT_FOUND",
        "The paper establishes that using self-attention causes a forty percent "
        "reduction in carbon emissions compared with recurrent networks.",
    ),
    AcceptanceCase(
        "training_contradict",
        "CONTRADICT",
        "The authors trained the base Transformer for 100,000 steps on only one "
        "NVIDIA P100 GPU rather than eight GPUs.",
    ),
)

SAFE_ERROR_CODES = {
    "AI_CONFIG_REQUIRED",
    "AI_CONFIG_INVALID",
    "AI_AUTH_FAILED",
    "AI_ACCESS_DENIED",
    "AI_QUOTA_EXCEEDED",
    "AI_RATE_LIMITED",
    "AI_MODEL_UNAVAILABLE",
    "AI_TIMEOUT",
    "AI_PROVIDER_FAILED",
    "INVALID_REQUEST",
    "COMPARISON_FAILED",
    "LLM_NOT_CONFIGURED",
    "ACCEPTANCE_BUDGET_EXHAUSTED",
}
STOP_ERROR_CODES = {
    "AI_AUTH_FAILED",
    "AI_ACCESS_DENIED",
    "AI_QUOTA_EXCEEDED",
    "AI_RATE_LIMITED",
    "AI_MODEL_UNAVAILABLE",
    "AI_CONFIG_INVALID",
}


def available_providers() -> list[str]:
    """Read the installed API contract, including PR #60's enum after integration."""
    from backend.src.user_ai import UserAIConfig

    annotation = UserAIConfig.model_fields["provider"].annotation
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [item.value for item in annotation]
    return list(get_args(annotation))


def make_report(args) -> dict:
    selected_cases = args.case or [case.case_id for case in CASES]
    thinking = getattr(args, "thinking", None) or "disabled"
    compare = getattr(args, "compare_thinking", False)
    rows = []
    for provider in available_providers():
        for case in CASES:
            selected = provider == args.provider and case.case_id in selected_cases
            rows.append(
                {
                    "provider": provider,
                    "case_id": case.case_id,
                    "selected": selected,
                    "expected": {
                        "http_status": 200,
                        "status": "COMPARED",
                        "verdict": case.expected_verdict,
                        "source_paper_id": "src-transformer",
                    },
                    "actual": None,
                    "outcome": "untested",
                    "reason": "live_not_enabled" if selected else "not_selected",
                    "duration_seconds": None,
                }
            )
            if provider == "deepseek":
                modes = ("disabled", "low") if compare else (thinking,)
                template = rows.pop()
                for mode in modes:
                    rows.append({**template, "thinking": mode})
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        revision = None
    return {
        "schema_version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "revision": revision or None,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mode": "live" if args.live else "plan",
        "scope": "Seeded parsed source; citation resolution, embedding, retrieval and judgement. "
        "PDF parsing and Audit extraction are outside this suite.",
        "configuration": {
            "provider": args.provider,
            "model": args.model,
            "region": args.region,
            "workspace": args.workspace,
        },
        "budget": {"max_calls": args.max_calls or 0, "calls_attempted": 0},
        "generation": (
            {
                "max_output_tokens": getattr(args, "max_output_tokens", None),
                "thinking": "compare" if compare else thinking,
                "default_token_caps": {"disabled": 2048, "enabled": 8192},
            }
            if args.provider == "deepseek"
            else None
        ),
        "cases": rows,
    }


def evaluate(case: AcceptanceCase, response) -> dict:
    """Check the API contract and verdict; never report raw errors or rationale."""
    from backend.src.models import CitationComparisonResponse, ComparisonStatus, VerdictEnum
    from pydantic import ValidationError

    result = {
        "outcome": "failed",
        "reason": "invalid_response",
        "actual": {
            "http_status": response.status_code,
            "status": None,
            "verdict": None,
            "evidence_count": 0,
            "error_code": None,
            "evidence_sha256": None,
        },
    }
    actual = result["actual"]
    try:
        body = response.json()
    except ValueError:
        return result
    if not isinstance(body, dict):
        return result
    if isinstance(body.get("status"), str) and body["status"] in {
        item.value for item in ComparisonStatus
    }:
        actual["status"] = body["status"]
    judgement = body.get("judgement")
    if (
        isinstance(judgement, dict)
        and isinstance(judgement.get("verdict"), str)
        and judgement["verdict"] in {item.value for item in VerdictEnum}
    ):
        actual["verdict"] = judgement["verdict"]
    if isinstance(body.get("evidence"), list):
        actual["evidence_count"] = len(body["evidence"])
    if response.status_code != 200:
        detail = body.get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        actual["error_code"] = (
            code if isinstance(code, str) and code in SAFE_ERROR_CODES else "UNEXPECTED_API_ERROR"
        )
        result["reason"] = "http_error"
        return result
    try:
        parsed = CitationComparisonResponse.model_validate(body)
    except ValidationError:
        return result
    if parsed.status != ComparisonStatus.COMPARED or parsed.judgement is None:
        result["reason"] = "comparison_incomplete"
    elif parsed.source_paper_id != "src-transformer":
        result["reason"] = "wrong_source"
    elif not parsed.evidence or any(not item.passage_text.strip() for item in parsed.evidence):
        result["reason"] = "missing_evidence"
    elif parsed.judgement.verdict.value != case.expected_verdict:
        result["reason"] = "verdict_mismatch"
    else:
        result.update(outcome="passed", reason="matched")
    if parsed.evidence:
        actual["evidence_sha256"] = hashlib.sha256(
            json.dumps([item.passage_text for item in parsed.evidence]).encode("utf-8")
        ).hexdigest()
    return result


@dataclass
class CallBudget:
    limit: int
    attempted: int = 0
    usage: list[dict] = field(default_factory=list)


def token_usage(result) -> dict:
    usage = getattr(result, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    values = {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    return {
        name: value if type(value) is int and value >= 0 else None for name, value in values.items()
    }


def usage_summary(records) -> dict:
    return {
        "calls_with_usage": sum(
            item.get("calls_with_usage", int(item.get("total_tokens") is not None))
            for item in records
        ),
        "calls_without_usage": sum(
            item.get("calls_without_usage", int(item.get("total_tokens") is None))
            for item in records
        ),
        **{
            name: (sum(values) if values else None)
            for name in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")
            for values in [[item[name] for item in records if item.get(name) is not None]]
        },
    }


@contextmanager
def enforce_budget(
    budget: CallBudget, *, provider=None, max_output_tokens=None, thinking="disabled"
):
    """Count the actual runtime calls, including any unexpected extra AI step."""
    from backend.src.services.user_ai_runtime import UserAIError, UserAIRuntime

    original = UserAIRuntime.create
    lock = Lock()

    def bounded_create(runtime, **kwargs):
        if runtime.failure is not None:
            return original(runtime, **kwargs)
        with lock:
            if budget.attempted >= budget.limit:
                runtime.failure = UserAIError(
                    "ACCEPTANCE_BUDGET_EXHAUSTED", "The acceptance call budget is exhausted."
                )
                raise runtime.failure
            budget.attempted += 1
        if provider == "deepseek":
            limit = max_output_tokens or (2048 if thinking == "disabled" else 8192)
            kwargs["max_tokens"] = min(kwargs.get("max_tokens") or limit, limit)
            kwargs["extra_body"] = {
                **kwargs.get("extra_body", {}),
                "thinking": {"type": "disabled" if thinking == "disabled" else "enabled"},
            }
            if thinking == "disabled":
                kwargs.pop("reasoning_effort", None)
            else:
                kwargs["reasoning_effort"] = thinking
                kwargs.pop("temperature", None)
        try:
            result = original(runtime, **kwargs)
        except Exception:
            budget.usage.append(token_usage(None))
            raise
        budget.usage.append(token_usage(result))
        if provider == "deepseek":
            # Current main predates PR #60's partial-generation rejection.
            choices = getattr(result, "choices", None)
            if not choices or getattr(choices[0], "finish_reason", None) != "stop":
                runtime.failure = UserAIError(
                    "AI_PROVIDER_FAILED", "The provider did not complete the acceptance response."
                )
                raise runtime.failure
        return result

    with patch.object(UserAIRuntime, "create", bounded_create):
        yield


@contextmanager
def scratch_library():
    """Restore storage globals afterwards; do not run startup/deletion recovery."""
    with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
        root = Path(tmp)
        stack.enter_context(patch.dict(os.environ, {"CLAIMTRACE_ENV_FILE": os.devnull}))
        from backend.src.config import get_settings
        from backend.src.storage import bib_document_store, paper_store, parsed_document_store

        get_settings.cache_clear()
        settings = get_settings()
        for name, value in {
            "upload_dir": root,
            "papers_file": root / "papers.json",
            "parsed_dir": root / "parsed",
        }.items():
            stack.enter_context(patch.object(settings, name, value))
        stack.enter_context(patch.object(paper_store, "PAPERS_FILE", root / "papers.json"))
        stack.enter_context(patch.object(parsed_document_store, "PARSED_DIR", root / "parsed"))
        stack.enter_context(patch.object(bib_document_store, "BIB_PARSED_DIR", root / "parsed/bib"))
        try:
            seed(root)
            yield
        finally:
            get_settings.cache_clear()


def seed(upload_dir: Path) -> None:
    """Write complete parsed fixtures into the already isolated stores."""
    from backend.src.models import (
        BibEntryRecord,
        PaperRecord,
        ParsedBibDocument,
        ParsedDocument,
        ParsedParagraph,
        ParseStatus,
    )
    from backend.src.storage.bib_document_store import save_bib_document
    from backend.src.storage.paper_store import create_paper
    from backend.src.storage.parsed_document_store import save_parsed_document

    now = datetime.now(UTC)
    document = ParsedDocument(
        paper_id="src-transformer",
        title=SOURCE_TITLE,
        authors=["Vaswani, Ashish"],
        year=2017,
        venue="NeurIPS",
        doi="10.5555/3295222.3295349",
        pages=1,
        paragraphs=[
            ParsedParagraph(text=text, page_start=1, page_end=1) for text in SOURCE_PARAGRAPHS
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="src-transformer",
            original_filename="attention.pdf",
            stored_filename="attention.pdf",
            file_path=str(upload_dir / "attention.pdf"),
            parsed_result_path=str(save_parsed_document(document)),
            file_type="pdf",
            file_size=1024,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )

    bibliography = ParsedBibDocument(
        paper_id="bib-manuscript",
        entries=[
            BibEntryRecord(
                key="vaswani2017attention",
                title=SOURCE_TITLE,
                authors=["Vaswani, Ashish"],
                year=2017,
                venue="NeurIPS",
                doi="10.5555/3295222.3295349",
            )
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="bib-manuscript",
            original_filename="references.bib",
            stored_filename="references.bib",
            file_path=str(upload_dir / "references.bib"),
            parsed_result_path=str(save_bib_document(bibliography)),
            file_type="bib",
            file_size=512,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )


def run_live(report: dict, config: dict, budget: CallBudget, *, report_path=None) -> None:
    from backend.src.main import app
    from fastapi.testclient import TestClient

    cases = {case.case_id: case for case in CASES}
    stop_reason = None
    # No lifespan context: acceptance must never run startup deletion recovery.
    client = TestClient(app)
    try:
        generation = report.get("generation") or {}
        for row in report["cases"]:
            with enforce_budget(
                budget,
                provider=config["provider"],
                max_output_tokens=generation.get("max_output_tokens"),
                thinking=row.get("thinking", "disabled"),
            ):
                if not row["selected"]:
                    continue
                if stop_reason or budget.attempted >= budget.limit:
                    row["reason"] = stop_reason or "budget_exhausted"
                    continue
                case = cases[row["case_id"]]
                started = time.perf_counter()
                usage_start = len(budget.usage)
                try:
                    response = client.post(
                        "/api/verify/citation",
                        json={
                            "claim": case.claim,
                            "citation_marker": r"\cite{vaswani2017attention}",
                            "bib_paper_id": "bib-manuscript",
                            "ai_config": config,
                        },
                    )
                    row.update(evaluate(case, response))
                except KeyboardInterrupt:
                    row["reason"] = stop_reason = "interrupted"
                except Exception:
                    row.update(outcome="failed", reason="request_exception")
                finally:
                    row["duration_seconds"] = round(time.perf_counter() - started, 3)
                    row["usage"] = usage_summary(budget.usage[usage_start:])
                code = (row["actual"] or {}).get("error_code")
                if code in STOP_ERROR_CODES:
                    stop_reason = "provider_unavailable"
                elif code == "ACCEPTANCE_BUDGET_EXHAUSTED":
                    row.update(outcome="untested", reason="budget_exhausted")
                    stop_reason = "budget_exhausted"
                if report_path is not None:
                    report["budget"]["calls_attempted"] = budget.attempted
                    report["usage"] = usage_summary(budget.usage)
                    write_report(report, report_path, quiet=True)
    finally:
        client.close()


def write_report(report: dict, target: Path, *, quiet=False) -> int:
    def counts(rows):
        return {
            outcome: sum(row["outcome"] == outcome for row in rows)
            for outcome in ("passed", "failed", "untested")
        }

    report["summary"] = counts(report["cases"])
    selected = counts([row for row in report["cases"] if row["selected"]])
    report["selected_summary"] = selected
    if report.get("generation"):
        modes = sorted({row["thinking"] for row in report["cases"] if row["selected"]})
        report["mode_comparison"] = {}
        for mode in modes:
            rows = [row for row in report["cases"] if row["selected"] and row["thinking"] == mode]
            durations = [
                row["duration_seconds"] for row in rows if row["duration_seconds"] is not None
            ]
            report["mode_comparison"][mode] = {
                **counts(rows),
                "completed_comparisons": sum(
                    (row["actual"] or {}).get("status") == "COMPARED" for row in rows
                ),
                "mean_duration_seconds": round(sum(durations) / len(durations), 3)
                if durations
                else None,
                "usage": usage_summary([row["usage"] for row in rows if "usage" in row]),
            }
        report["evidence_comparison"] = {}
        for case in CASES:
            hashes = [
                (row["actual"] or {}).get("evidence_sha256")
                for row in report["cases"]
                if row["selected"] and row["case_id"] == case.case_id
            ]
            report["evidence_comparison"][case.case_id] = (
                len(set(hashes)) == 1 if len(hashes) > 1 and all(hashes) else None
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["cases"]:
        if quiet:
            break
        if any(item["selected"] for item in report["cases"]) and not row["selected"]:
            continue
        actual = (row["actual"] or {}).get("verdict") or "-"
        print(
            f"{row['provider']:12} {row.get('thinking', '-'):8} "
            f"{row['case_id']:20} {row['outcome']:8} "
            f"expected={row['expected']['verdict']:10} actual={actual:10} {row['reason']}"
        )
    if not quiet:
        print(f"Matrix: {report['summary']}; selected: {selected}")
        print(f"Provider calls attempted: {report['budget']['calls_attempted']}; report: {target}")
    if selected["failed"]:
        return 1
    return 2 if selected["untested"] or not sum(selected.values()) else 0


def main(argv=None) -> int:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--provider", choices=available_providers())
    arguments.add_argument("--model")
    arguments.add_argument("--region")
    arguments.add_argument("--workspace")
    arguments.add_argument("--case", action="append", choices=[case.case_id for case in CASES])
    arguments.add_argument("--live", action="store_true")
    arguments.add_argument("--max-calls", type=int)
    arguments.add_argument(
        "--max-output-tokens",
        type=int,
        help="DeepSeek only: 1-32768 generated tokens; default 2048 disabled / 8192 thinking.",
    )
    arguments.add_argument(
        "--thinking",
        choices=("disabled", "low", "high", "max"),
        help="DeepSeek thinking effort; default disabled.",
    )
    arguments.add_argument(
        "--compare-thinking",
        action="store_true",
        help="DeepSeek: compare disabled and low on the same cases and shared budget.",
    )
    arguments.add_argument("--report", type=Path, default=Path("verify-acceptance-report.json"))
    args = arguments.parse_args(argv)
    if args.live and (
        not args.provider or not args.model or not args.max_calls or args.max_calls < 1
    ):
        arguments.error("--live requires --provider, --model and a positive --max-calls budget")
    if args.max_calls is not None and args.max_calls < 0:
        arguments.error("--max-calls cannot be negative")
    if args.max_output_tokens is not None and (
        args.provider != "deepseek" or not 1 <= args.max_output_tokens <= 32768
    ):
        arguments.error(
            "--max-output-tokens requires --provider deepseek and a value from 1 to 32768"
        )
    if (args.thinking or args.compare_thinking) and args.provider != "deepseek":
        arguments.error("Thinking options require --provider deepseek")
    if args.thinking and args.compare_thinking:
        arguments.error("Select --thinking or --compare-thinking, not both")
    report = make_report(args)
    report["run_status"] = "awaiting_credentials" if args.live else "planned"
    budget = CallBudget(args.max_calls or 0)
    if args.live:
        from backend.src.user_ai import UserAIConfig
        from pydantic import ValidationError

        write_report(report, args.report, quiet=True)

        config = {"provider": args.provider, "model": args.model}
        for name in ("region", "workspace"):
            if getattr(args, name) is not None:
                config[name] = getattr(args, name)
        try:
            UserAIConfig.model_validate({**config, "api_key": "validation-only"})
            if not sys.stdin.isatty():
                raise ValueError("A hidden interactive key prompt is required.")
            key = getpass.getpass("API key (not saved; live calls spend your credits): ")
            UserAIConfig.model_validate({**config, "api_key": key})
        except (ValidationError, ValueError, EOFError, KeyboardInterrupt):
            for row in report["cases"]:
                if row["selected"]:
                    row["reason"] = "configuration_or_credentials_unavailable"
        else:
            report["run_status"] = "running"
            try:
                with scratch_library():
                    run_live(report, {**config, "api_key": key}, budget, report_path=args.report)
            except KeyboardInterrupt:
                reason = "interrupted"
            except Exception:
                reason = "setup_failed"
            else:
                reason = None
            if reason:
                for row in report["cases"]:
                    if row["selected"] and row["outcome"] == "untested":
                        row["reason"] = reason
            del key
        report["run_status"] = "completed"
    report["budget"]["calls_attempted"] = budget.attempted
    report["usage"] = usage_summary(budget.usage)
    return write_report(report, args.report)


if __name__ == "__main__":
    sys.exit(main())
