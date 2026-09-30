"""Offline coverage for LLM-based reference metadata segmentation."""

import json
from types import SimpleNamespace

from backend.src.services.reference_metadata_segmenter import (
    SegmentationStatus,
    segment_reference_metadata,
)


class FakeCompletions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.calls.append(kwargs)
        if isinstance(self.owner.reply, Exception):
            raise self.owner.reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.owner.reply))]
        )


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.chat = SimpleNamespace(completions=FakeCompletions(self))


def test_segments_fields_in_any_order_and_uses_json_mode():
    raw = "Journal of Testing, 2022. J. Smith. Example title."
    client = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": ["J. Smith"],
                        "title": "Example title",
                        "venue": "Journal of Testing",
                        "year": "2022",
                        "doi": None,
                    }
                ]
            }
        )
    )

    outcome = segment_reference_metadata([raw], client=client, model="test-model")[0]

    assert outcome.status is SegmentationStatus.SEGMENTED
    assert outcome.metadata.title == "Example title"
    assert outcome.metadata.authors == ["J. Smith"]
    assert outcome.metadata.venue == "Journal of Testing"
    assert outcome.metadata.year == 2022
    assert outcome.model == "test-model"
    assert client.calls[0]["response_format"] == {"type": "json_object"}
    assert client.calls[0]["temperature"] == 0.0
    assert raw in client.calls[0]["messages"][1]["content"]


def test_rejects_invented_field_but_keeps_valid_fields():
    client = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": [],
                        "title": "A title not present in the reference",
                        "venue": None,
                        "year": "2024",
                        "doi": None,
                    }
                ]
            }
        )
    )

    outcome = segment_reference_metadata(
        ["Smith. Existing title. 2024."], client=client, model="test-model"
    )[0]

    assert outcome.status is SegmentationStatus.PARTIAL
    assert outcome.metadata.title is None
    assert outcome.metadata.year == 2024
    assert "title" in outcome.diagnostic


def test_rejects_rewritten_title_as_validation_failure():
    client = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": [],
                        "title": "Translated and rewritten title",
                        "venue": None,
                        "year": None,
                        "doi": None,
                    }
                ]
            }
        )
    )

    outcome = segment_reference_metadata(
        ["Smith. Original title."], client=client, model="test-model"
    )[0]

    assert outcome.status is SegmentationStatus.VALIDATION_FAILED
    assert outcome.metadata.title is None


def test_provider_failure_returns_one_failure_per_input():
    client = FakeLLM(RuntimeError("upstream unavailable"))
    outcomes = segment_reference_metadata(
        ["First reference", "Second reference"], client=client, model="test-model"
    )

    assert [outcome.status for outcome in outcomes] == [
        SegmentationStatus.MODEL_ERROR,
        SegmentationStatus.MODEL_ERROR,
    ]


def test_missing_and_duplicate_item_ids_do_not_hide_valid_item():
    client = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "item_id": "0",
                        "authors": [],
                        "title": "First",
                        "venue": None,
                        "year": None,
                        "doi": None,
                    },
                    {
                        "item_id": "1",
                        "authors": [],
                        "title": "Second",
                        "venue": None,
                        "year": None,
                        "doi": None,
                    },
                    {
                        "item_id": "1",
                        "authors": [],
                        "title": "Second",
                        "venue": None,
                        "year": None,
                        "doi": None,
                    },
                ]
            }
        )
    )

    outcomes = segment_reference_metadata(
        ["First.", "Second.", "Third."], client=client, model="test-model"
    )

    assert outcomes[0].status is SegmentationStatus.SEGMENTED
    assert outcomes[1].status is SegmentationStatus.INVALID_RESPONSE
    assert outcomes[2].status is SegmentationStatus.INVALID_RESPONSE


def test_no_client_is_explicit_and_does_not_raise():
    outcomes = segment_reference_metadata(
        ["First reference", "Second reference"], client=None, model="unused"
    )

    assert len(outcomes) == 2
    assert all(outcome.status is SegmentationStatus.NO_CLIENT for outcome in outcomes)


def test_batches_keep_global_item_ids():
    class EchoCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            request = json.loads(kwargs["messages"][1]["content"])
            items = [
                {
                    "item_id": item["item_id"],
                    "authors": [],
                    "title": item["raw_text"],
                    "venue": None,
                    "year": None,
                    "doi": None,
                }
                for item in request["items"]
            ]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps({"items": items}))
                    )
                ]
            )

    completions = EchoCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    raw = ["One", "Two", "Three"]

    outcomes = segment_reference_metadata(
        raw, client=client, model="test-model", batch_size=2
    )

    assert len(completions.calls) == 2
    assert [outcome.metadata.title for outcome in outcomes] == raw
