"""Tests for verifier.py — the verdict/failure-status contract.

Fully offline: the LLM client is a fake at the ``chat.completions.create``
seam. The point of this file is that **no failure may ever masquerade as a
verdict**, so several tests exist purely to pin a specific fabrication path
that used to return a real-looking ``NOT_FOUND``.
"""

import json
from types import SimpleNamespace

import pytest

from engine.retriever import RetrievalResult
from engine.verifier import (
    Verdict,
    VerificationResult,
    VerificationStatus,
    Verifier,
)

# The prompt's own boundary between the cited source and the claim. Splitting on
# it is what lets a test prove *where* a string landed, not merely that it is
# present somewhere in the prompt.
PROMPT_SPLIT = "CLAIM (from the paper being audited):"

ALPHA = "ALPHA-PASSAGE-SENTINEL"
BETA = "BETA-PASSAGE-SENTINEL"
CLAIM = "GAMMA-CLAIM-SENTINEL"


# ── Fakes --------------------------------------------------------


class FakeCompletions:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        if isinstance(self._owner.reply, Exception):
            raise self._owner.reply
        message = SimpleNamespace(content=self._owner.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLM:
    """Minimal OpenAI-compatible client: ``.chat.completions.create(...)``."""

    def __init__(self, reply='{"label": "SUPPORT", "rationale": "Because."}'):
        self.reply = reply
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=FakeCompletions(self))

    @property
    def prompt(self) -> str:
        assert self.calls, "the model was never called"
        return self.calls[-1]["messages"][0]["content"]


def result_at(rank: int, passage: str, score: float = 0.9) -> RetrievalResult:
    return RetrievalResult(passage=passage, score=score, rank=rank, passage_index=rank - 1)


@pytest.fixture
def verifier():
    return Verifier()


# ── The Verdict enum is frozen -----------------------------------


class TestVerdictEnumContract:
    def test_verdict_is_still_a_closed_four_member_set(self):
        """Adding a member breaks three consumers outside this package.

        ``frontend/src/components/VerdictBadge.tsx`` indexes a
        ``Record<Verdict, string>`` with no runtime guard,
        ``frontend/src/types/api.ts`` declares the same four literals, and
        ``backend/src/models.py`` mirrors this as ``VerdictEnum``. A failure to
        judge belongs in ``VerificationStatus``, never here.
        """
        assert {member.value for member in Verdict} == {
            "SUPPORT",
            "PARTIAL",
            "CONTRADICT",
            "NOT_FOUND",
        }


# ── The result invariant -----------------------------------------


class TestVerificationResultInvariant:
    def test_judged_status_requires_a_verdict(self):
        with pytest.raises(ValueError, match="JUDGED requires a verdict"):
            VerificationResult(claim="c", status=VerificationStatus.JUDGED)

    def test_failure_status_must_not_carry_a_verdict(self):
        with pytest.raises(ValueError, match="must not carry a verdict"):
            VerificationResult(
                claim="c",
                status=VerificationStatus.MODEL_ERROR,
                verdict=Verdict.SUPPORT,
            )

    def test_failed_constructor_refuses_a_judged_status(self):
        with pytest.raises(ValueError, match="judged"):
            VerificationResult.failed(
                claim="c", status=VerificationStatus.JUDGED, rationale="r"
            )

    def test_failed_constructor_cannot_express_a_verdict(self):
        """``failed`` has no ``verdict`` or ``best_match`` parameter at all."""
        result = VerificationResult.failed(
            claim="c", status=VerificationStatus.NO_CLIENT, rationale="r"
        )
        assert result.verdict is None
        assert result.confidence == 0.0
        assert result.best_match is None

    def test_positional_misuse_is_a_loud_type_error(self):
        """``VerificationResult(claim, verdict)`` used to build a wrong result."""
        with pytest.raises(TypeError, match="status must be a VerificationStatus"):
            VerificationResult("c", Verdict.SUPPORT)

    def test_a_bare_string_is_not_accepted_as_a_verdict(self):
        with pytest.raises(TypeError, match="verdict must be a Verdict"):
            VerificationResult(
                claim="c",
                status=VerificationStatus.JUDGED,
                verdict="SUPPORT",
            )


# ── The retrieved passages actually reach the model --------------


class TestPromptPlumbing:
    """Confirms the retrieved source text is what the model is shown."""

    def test_passages_land_in_the_source_slot_not_the_claim_slot(self):
        client = FakeLLM()
        results = [result_at(1, ALPHA), result_at(2, BETA)]

        verifier = Verifier()
        verifier.verify_with_retrieval(CLAIM, results, client=client, top_n=2)

        source_slot, claim_slot = client.prompt.split(PROMPT_SPLIT)
        # Asserting *which half* is what proves placement rather than mere presence.
        assert ALPHA in source_slot
        assert BETA in source_slot
        assert CLAIM in claim_slot
        assert CLAIM not in source_slot

    def test_passage_headers_carry_rank_and_similarity(self):
        client = FakeLLM()
        results = [result_at(1, ALPHA, score=0.9), result_at(2, BETA, score=0.8)]

        Verifier().verify_with_retrieval(CLAIM, results, client=client, top_n=2)

        assert "[Passage 1, similarity=0.900]" in client.prompt
        assert "[Passage 2, similarity=0.800]" in client.prompt

    def test_context_is_capped_at_top_n(self):
        client = FakeLLM()
        results = [result_at(1, ALPHA), result_at(2, BETA), result_at(3, "GAMMA-X")]

        Verifier().verify_with_retrieval(CLAIM, results, client=client, top_n=2)

        assert ALPHA in client.prompt
        assert BETA in client.prompt
        assert "GAMMA-X" not in client.prompt

    def test_context_preserves_retrieval_order(self):
        client = FakeLLM()
        results = [result_at(1, ALPHA), result_at(2, BETA)]

        Verifier().verify_with_retrieval(CLAIM, results, client=client, top_n=2)

        assert client.prompt.index(ALPHA) < client.prompt.index(BETA)

    def test_source_text_used_is_exactly_what_was_sent(self):
        client = FakeLLM()
        results = [result_at(1, ALPHA)]

        result = Verifier().verify_with_retrieval(CLAIM, results, client=client, top_n=1)

        assert result.source_text_used == "[Passage 1, similarity=0.900]\n" + ALPHA
        assert result.source_text_used in client.prompt

    def test_prompt_is_built_correctly(self, verifier):
        prompt = verifier._build_prompt("Claim text", "Source text")
        for text in ("Claim text", "Source text", "SUPPORT", "PARTIAL", "CONTRADICT",
                     "NOT_FOUND"):
            assert text in prompt


# ── The judged path ----------------------------------------------


class TestJudgedPath:
    def test_valid_reply_produces_a_judged_result(self):
        client = FakeLLM('{"label": "SUPPORT", "rationale": "The passage states this."}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.JUDGED
        assert result.verdict is Verdict.SUPPORT
        assert result.confidence == 0.85
        assert result.rationale == "The passage states this."

    def test_a_judged_result_carries_the_best_match(self):
        results = [result_at(1, ALPHA)]

        result = Verifier().verify_with_retrieval(CLAIM, results, client=FakeLLM(), top_n=1)

        assert result.best_match is results[0]

    @pytest.mark.parametrize(
        "label", ["SUPPORT", "PARTIAL", "CONTRADICT", "NOT_FOUND"]
    )
    def test_every_label_round_trips_unchanged(self, label):
        """The engine never overrides the model's own label."""
        client = FakeLLM('{"label": "%s", "rationale": "r"}' % label)

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.JUDGED
        assert result.verdict.value == label

    def test_not_found_carries_the_lower_confidence_band(self):
        client = FakeLLM('{"label": "NOT_FOUND", "rationale": "r"}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.verdict is Verdict.NOT_FOUND
        assert result.confidence == 0.3

    @pytest.mark.parametrize("raw_label", ["  support ", "support", "SUPPORT\n"])
    def test_label_is_case_and_whitespace_insensitive(self, raw_label):
        """Deliberate leniency: trailing whitespace is not a model failure.

        The reply is built with ``json.dumps`` so a label containing a newline
        is escaped the way a real provider would send it; interpolating it raw
        would produce malformed JSON and test the wrong path.
        """
        client = FakeLLM(json.dumps({"label": raw_label, "rationale": "r"}))

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.JUDGED
        assert result.verdict is Verdict.SUPPORT

    def test_missing_rationale_falls_back_to_a_placeholder(self):
        client = FakeLLM('{"label": "SUPPORT"}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.JUDGED
        assert result.rationale == "No rationale provided."

    def test_extra_keys_are_ignored(self):
        client = FakeLLM('{"label": "PARTIAL", "rationale": "r", "score": 0.4, "x": [1]}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.JUDGED
        assert result.verdict is Verdict.PARTIAL


# ── No failure path may fabricate a verdict ----------------------


class TestFailurePathsNeverFabricate:
    def test_no_client_is_not_a_verdict(self, verifier):
        result = verifier.verify("claim", "source", client=None)

        assert result.status is VerificationStatus.NO_CLIENT
        assert result.verdict is None
        assert result.confidence == 0.0

    def test_empty_retrieval_is_not_a_verdict(self):
        """Used to return NOT_FOUND without ever calling the model."""
        client = FakeLLM()

        result = Verifier().verify_with_retrieval("claim", [], client=client)

        assert result.status is VerificationStatus.NO_EVIDENCE
        assert result.verdict is None
        assert client.calls == []

    def test_no_client_via_retrieval_is_not_a_verdict(self):
        results = [result_at(1, ALPHA)]

        result = Verifier().verify_with_retrieval("claim", results, client=None)

        assert result.status is VerificationStatus.NO_CLIENT
        assert result.verdict is None

    def test_whitespace_only_passages_are_no_evidence(self):
        """A context of bare headers is not evidence."""
        client = FakeLLM()
        results = [result_at(1, "   "), result_at(2, "\n\t")]

        result = Verifier().verify_with_retrieval("claim", results, client=client)

        assert result.status is VerificationStatus.NO_EVIDENCE
        assert result.verdict is None
        assert client.calls == []

    def test_blank_passages_do_not_consume_a_top_n_slot(self):
        client = FakeLLM()
        results = [result_at(1, "   "), result_at(2, ALPHA)]

        result = Verifier().verify_with_retrieval("claim", results, client=client, top_n=1)

        assert result.status is VerificationStatus.JUDGED
        assert ALPHA in client.prompt

    @pytest.mark.parametrize("top_n", [0, -1])
    def test_non_positive_top_n_is_no_evidence(self, top_n):
        client = FakeLLM()
        results = [result_at(1, ALPHA)]

        result = Verifier().verify_with_retrieval(
            "claim", results, client=client, top_n=top_n
        )

        assert result.status is VerificationStatus.NO_EVIDENCE
        assert result.verdict is None
        assert client.calls == []

    def test_blank_claim_is_no_evidence(self):
        client = FakeLLM()

        result = Verifier().verify("   ", "source", client=client)

        assert result.status is VerificationStatus.NO_EVIDENCE
        assert result.verdict is None
        assert client.calls == []

    def test_blank_source_is_no_evidence(self):
        client = FakeLLM()

        result = Verifier().verify("claim", "  \n ", client=client)

        assert result.status is VerificationStatus.NO_EVIDENCE
        assert result.verdict is None
        assert client.calls == []

    def test_model_error_is_not_a_verdict(self):
        client = FakeLLM(RuntimeError("upstream 502"))

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.MODEL_ERROR
        assert result.verdict is None
        assert "502" in result.rationale

    def test_unparseable_reply_is_not_a_verdict(self):
        """Used to be reported as a real NOT_FOUND verdict."""
        client = FakeLLM("not json at all")

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_RESPONSE
        assert result.verdict is None
        assert "not json at all" in result.rationale

    def test_reply_without_a_label_is_not_a_verdict(self):
        """Used to silently default the label to NOT_FOUND."""
        client = FakeLLM('{"rationale": "sounds fine to me"}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_LABEL
        assert result.verdict is None

    def test_out_of_enum_label_is_not_a_verdict(self):
        """Used to raise ValueError straight through the caller."""
        client = FakeLLM('{"label": "SUPPORTS", "rationale": "r"}')

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_LABEL
        assert result.verdict is None
        assert "SUPPORTS" in result.rationale

    @pytest.mark.parametrize("raw_label", ["   ", "", None, 7])
    def test_unusable_label_is_not_a_verdict(self, raw_label):
        client = FakeLLM(json.dumps({"label": raw_label, "rationale": "r"}))

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_LABEL
        assert result.verdict is None

    def test_none_content_is_not_a_verdict(self):
        """Used to raise TypeError out of ``json.loads(None)``."""
        client = FakeLLM(None)

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_RESPONSE
        assert result.verdict is None

    @pytest.mark.parametrize("reply", ['["SUPPORT"]', '"SUPPORT"', "42"])
    def test_non_object_json_is_not_a_verdict(self, reply):
        """Used to hit the fabricated NOT_FOUND via AttributeError."""
        client = FakeLLM(reply)

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_RESPONSE
        assert result.verdict is None

    def test_a_reply_with_no_readable_content_is_not_a_verdict(self):
        broken = SimpleNamespace(choices=[])
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: broken))
        )

        result = Verifier().verify("claim", "source", client=client)

        assert result.status is VerificationStatus.INVALID_RESPONSE
        assert result.verdict is None


class TestNoFailurePathProducesAVerdict:
    """The teammate's requirement, encoded literally.

    Each scenario is a call that fails to reach a judgement. The per-path tests
    above say *which* status each one earns; this says none of them may ever
    come back looking like a verdict.
    """

    @staticmethod
    def scenarios() -> dict:
        v = Verifier()
        blank = [result_at(1, "   ")]
        real = [result_at(1, ALPHA)]
        return {
            "no_client": lambda: v.verify("c", "s", client=None),
            "blank_claim": lambda: v.verify(" ", "s", client=FakeLLM()),
            "blank_source": lambda: v.verify("c", " ", client=FakeLLM()),
            "empty_retrieval": lambda: v.verify_with_retrieval("c", [], client=FakeLLM()),
            "blank_passages": lambda: v.verify_with_retrieval(
                "c", blank, client=FakeLLM()
            ),
            "top_n_zero": lambda: v.verify_with_retrieval(
                "c", real, client=FakeLLM(), top_n=0
            ),
            "model_error": lambda: v.verify(
                "c", "s", client=FakeLLM(RuntimeError("boom"))
            ),
            "bad_json": lambda: v.verify("c", "s", client=FakeLLM("nope")),
            "missing_label": lambda: v.verify(
                "c", "s", client=FakeLLM('{"rationale":"r"}')
            ),
            "bad_label": lambda: v.verify(
                "c", "s", client=FakeLLM('{"label":"SUPPORTS"}')
            ),
            "none_content": lambda: v.verify("c", "s", client=FakeLLM(None)),
            "non_object_json": lambda: v.verify(
                "c", "s", client=FakeLLM('["SUPPORT"]')
            ),
        }

    def test_every_failure_scenario_withholds_a_verdict(self):
        for name, scenario in self.scenarios().items():
            result = scenario()
            assert result.status is not VerificationStatus.JUDGED, name
            assert result.verdict is None, name

    def test_every_failure_scenario_withholds_confidence_and_best_match(self):
        """A failure must not imply certainty, nor name a decisive passage."""
        for name, scenario in self.scenarios().items():
            result = scenario()
            assert result.confidence == 0.0, name
            assert result.best_match is None, name

    def test_no_failure_scenario_raises(self):
        for name, scenario in self.scenarios().items():
            scenario()  # must not raise
