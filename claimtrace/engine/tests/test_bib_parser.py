"""Tests for bib_parser.py."""

from pathlib import Path

import pytest

from engine.src.bib_parser import (
    BibEntry,
    _clean_title,
    _parse_authors,
    _parse_year,
    find_entry_by_key,
    find_entry_by_title,
    parse_bib_text,
)


# ── Sample BibTeX ──────────────────────────────────────────

SAMPLE_BIB = r"""
@article{wei2022emergent,
  title={Emergent Abilities of Large Language Models},
  author={Wei, Jason and Tay, Yi and Bommasani, Rishi and Raffel, Colin and Zoph, Barret and Borgeaud, Sebastian and Yogatama, Dani and Bosma, Maarten and Zhou, Denny and Metzler, Donald and others},
  year={2022},
  journal={Transactions on Machine Learning Research}
}

@inproceedings{vaswani2017attention,
  title={Attention is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki and Uszkoreit, Jakob and Jones, Llion and Gomez, Aidan N and Kaiser, Lukasz and Polosukhin, Illia},
  booktitle={Advances in Neural Information Processing Systems},
  year={2017},
  pages={5998--6008},
  volume={30}
}

@misc{brown2020language,
  title={Language Models are Few-Shot Learners},
  author={Brown, Tom B. and Mann, Benjamin and Ryder, Nick and Subbiah, Melanie and Kaplan, Jared and Dhariwal, Prafulla and others},
  year={2020},
  howpublished={arXiv preprint arXiv:2005.14165},
  url={https://arxiv.org/abs/2005.14165}
}
"""


# ── Unit tests ─────────────────────────────────────────────


class TestParseBibText:
    def test_parses_all_entries(self):
        entries = parse_bib_text(SAMPLE_BIB)
        assert len(entries) == 3

    def test_extracts_entry_type(self):
        entries = parse_bib_text(SAMPLE_BIB)
        types = {e.entry_type for e in entries}
        assert types == {"article", "inproceedings", "misc"}

    def test_extracts_key(self):
        entries = parse_bib_text(SAMPLE_BIB)
        keys = {e.key for e in entries}
        assert "wei2022emergent" in keys
        assert "vaswani2017attention" in keys

    def test_extracts_title(self):
        entries = parse_bib_text(SAMPLE_BIB)
        wei = find_entry_by_key(entries, "wei2022emergent")
        assert wei is not None
        assert "Emergent Abilities" in wei.title

    def test_title_cleans_latex_commands(self):
        entries = parse_bib_text(
            r'@article{test, title={\textit{Important} \textbf{Result}: A Study}, author={}, year={2024}}'
        )
        assert len(entries) == 1
        assert "Important Result: A Study" in entries[0].title

    def test_extracts_authors_last_first_format(self):
        entries = parse_bib_text(SAMPLE_BIB)
        wei = find_entry_by_key(entries, "wei2022emergent")
        assert wei is not None
        assert len(wei.authors) > 0
        assert wei.authors[0].startswith("Wei")

    def test_extracts_year(self):
        entries = parse_bib_text(SAMPLE_BIB)
        wei = find_entry_by_key(entries, "wei2022emergent")
        assert wei is not None
        assert wei.year == 2022

    def test_extracts_venue(self):
        entries = parse_bib_text(SAMPLE_BIB)
        wei = find_entry_by_key(entries, "wei2022emergent")
        assert wei is not None
        assert "Transactions on Machine Learning Research" in wei.venue

    def test_extracts_doi_and_url(self):
        entries = parse_bib_text(SAMPLE_BIB)
        brown = find_entry_by_key(entries, "brown2020language")
        assert brown is not None
        assert "arxiv" in brown.url

    def test_extracts_pages(self):
        entries = parse_bib_text(SAMPLE_BIB)
        vaswani = find_entry_by_key(entries, "vaswani2017attention")
        assert vaswani is not None
        assert vaswani.pages == "5998--6008"

    def test_author_last_names(self):
        entries = parse_bib_text(SAMPLE_BIB)
        wei = find_entry_by_key(entries, "wei2022emergent")
        assert wei is not None
        assert wei.first_author_last_name == "wei"
        assert "bommasani" in wei.author_last_names


class TestCleanTitle:
    def test_removes_textit(self):
        assert _clean_title(r"\textit{Fast} and Accurate") == "Fast and Accurate"

    def test_removes_braces(self):
        assert _clean_title("{C}onvolutional {N}eural Networks") == "Convolutional Neural Networks"

    def test_collapses_whitespace(self):
        assert _clean_title("Hello   \n  World") == "Hello World"


class TestParseAuthors:
    def test_last_first_format(self):
        authors = _parse_authors("Wei, Jason and Tay, Yi")
        assert len(authors) == 2
        assert authors[0] == "Wei, Jason"

    def test_first_last_format(self):
        authors = _parse_authors("Jason Wei and Yi Tay")
        assert len(authors) == 2

    def test_mixed_format(self):
        authors = _parse_authors("Wei, Jason and Yi Tay and Bommasani, Rishi")
        assert len(authors) == 3

    def test_single_author(self):
        authors = _parse_authors("Smith, John")
        assert len(authors) == 1


class TestParseYear:
    def test_plain_year(self):
        assert _parse_year("2024") == 2024

    def test_year_in_text(self):
        assert _parse_year("published in 2023") == 2023

    def test_no_year(self):
        assert _parse_year("no year here") is None


class TestFindEntry:
    @pytest.fixture
    def entries(self):
        return parse_bib_text(SAMPLE_BIB)

    def test_find_by_key_exact(self, entries):
        e = find_entry_by_key(entries, "wei2022emergent")
        assert e is not None
        assert e.key == "wei2022emergent"

    def test_find_by_key_case_insensitive(self, entries):
        e = find_entry_by_key(entries, "WEI2022EMERGENT")
        assert e is not None

    def test_find_by_key_missing(self, entries):
        assert find_entry_by_key(entries, "nonexistent") is None

    def test_find_by_title_fuzzy(self, entries):
        e = find_entry_by_title(entries, "Emergent Abilities of Large Language Models")
        assert e is not None
        assert "wei2022" in e.key

    def test_find_by_title_partial(self, entries):
        e = find_entry_by_title(entries, "attention is all you need")
        assert e is not None
        assert "vaswani" in e.key

    def test_find_by_title_no_match(self, entries):
        e = find_entry_by_title(entries, "Completely Unrelated Research Paper Title")
        assert e is None
