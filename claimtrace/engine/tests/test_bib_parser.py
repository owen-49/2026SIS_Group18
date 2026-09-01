"""Tests for bib_parser.py."""

from pathlib import Path

import pytest

from engine.bib_parser import (
    BibEntry,
    _clean_title,
    _extract_last_name,
    _normalize_author_name,
    _parse_authors,
    _parse_year,
    find_entry_by_key,
    find_entry_by_title,
    parse_bib_file,
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


# ── @string macro and # concatenation ────────────────────────


class TestStringMacros:
    def test_string_macro_expansion(self):
        entries = parse_bib_text(r"""
@string{jmlr = "Journal of Machine Learning Research"}
@article{smith2024,
  title={Deep Learning Advances},
  author={Smith, John},
  journal=jmlr,
  year={2024}
}
""")
        assert len(entries) == 1
        assert entries[0].venue == "Journal of Machine Learning Research"

    def test_string_macro_in_concatenation(self):
        entries = parse_bib_text(r"""
@string{acm = "ACM"}
@inproceedings{doe2024,
  title={Systems Research},
  author={Doe, Jane},
  booktitle=acm # " SIGOPS Operating Systems Review",
  year={2024}
}
""")
        assert len(entries) == 1
        assert "ACM SIGOPS" in entries[0].venue

    def test_multiple_string_macros(self):
        entries = parse_bib_text(r"""
@string{aaai = "AAAI Conference on Artificial Intelligence"}
@string{aaai_press = "AAAI Press"}
@article{test2024,
  title={Test},
  author={Test, Author},
  journal=aaai,
  publisher=aaai_press,
  year={2024}
}
""")
        assert len(entries) == 1
        assert "AAAI Conference" in entries[0].venue
        assert entries[0].publisher == "AAAI Press"

    def test_macro_case_insensitive(self):
        entries = parse_bib_text(r"""
@string{VLDB = "Very Large Data Bases"}
@article{test2024,
  title={Test},
  author={A, B},
  journal=vldb,
  year={2024}
}
""")
        assert entries[0].venue == "Very Large Data Bases"


class TestConcatenation:
    def test_hash_concat_two_strings(self):
        entries = parse_bib_text(r"""
@article{test2024,
  title={Test},
  author={A, B},
  journal="Journal of " # "Machine Learning",
  year={2024}
}
""")
        assert "Journal of Machine Learning" in entries[0].venue

    def test_hash_concat_three_parts(self):
        entries = parse_bib_text(r"""
@article{test2024,
  title={Test},
  author={A, B},
  journal="Part A " # "Part B " # "Part C",
  year={2024}
}
""")
        assert "Part A Part B Part C" in entries[0].venue


# ── @comment entries ─────────────────────────────────────────


class TestCommentEntries:
    def test_comment_skipped(self):
        entries = parse_bib_text(r"""
@comment{This is a comment that should be ignored}
@article{real2024,
  title={Real Paper},
  author={Author, Name},
  year={2024}
}
""")
        assert len(entries) == 1
        assert entries[0].key == "real2024"

    def test_multiple_comments_skipped(self):
        entries = parse_bib_text(r"""
@comment{JabRef meta data}
@comment{Another comment}
@article{test2024,
  title={Test},
  author={Test, T},
  year={2024}
}
@comment{trailing comment}
""")
        assert len(entries) == 1


# ── Special character handling ───────────────────────────────


class TestSpecialCharacters:
    def test_latex_dieresis(self):
        assert "o" in _clean_title(r'Sch\"{o}nbein')

    def test_latex_acute_accent(self):
        assert "e" in _clean_title(r"Universit\'{e} de Montr\'{e}al")
        assert "Universite de Montreal" == _clean_title(r"Universit\'{e} de Montr\'{e}al")

    def test_latex_tilde(self):
        assert "n" in _clean_title(r"Se\~{n}or")

    def test_latex_circumflex(self):
        assert "e" in _clean_title(r"f\^{e}te")

    def test_tex_dashes(self):
        result = _clean_title("Foo--Bar---Baz")
        assert "–" in result  # en-dash
        assert "—" in result  # em-dash

    def test_escaped_special_chars(self):
        result = _clean_title(r"Price \$100 \& Free \% off \_ test \#1")
        assert "$" in result
        assert "&" in result
        assert "%" in result
        assert "_" in result
        assert "#" in result


# ── Author name normalization ─────────────────────────────────


class TestAuthorNormalization:
    def test_first_last_to_last_first(self):
        assert _normalize_author_name("Jason Wei") == "Wei, Jason"

    def test_first_middle_last(self):
        assert _normalize_author_name("Tom B. Brown") == "Brown, Tom B."

    def test_already_last_first(self):
        assert _normalize_author_name("Wei, Jason") == "Wei, Jason"

    def test_single_name(self):
        assert _normalize_author_name("Aristotle") == "Aristotle"

    def test_parse_authors_normalizes(self):
        authors = _parse_authors("Jason Wei and Yi Tay and Rishi Bommasani")
        assert authors[0] == "Wei, Jason"
        assert authors[1] == "Tay, Yi"
        assert authors[2] == "Bommasani, Rishi"

    def test_extract_last_name_from_normalized(self):
        assert _extract_last_name("Wei, Jason") == "wei"
        assert _extract_last_name("Jason Wei") == "wei"
        assert _extract_last_name("Brown, Tom B.") == "brown"


# ── File parsing ─────────────────────────────────────────────


class TestParseBibFile:
    def test_parses_file(self, tmp_path):
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(r"""
@article{test2024,
  title={A Test Paper},
  author={Doe, John},
  year={2024}
}
""", encoding="utf-8")
        entries = parse_bib_file(bib_file)
        assert len(entries) == 1
        assert entries[0].key == "test2024"
        assert entries[0].title == "A Test Paper"

    def test_parses_file_with_macros(self, tmp_path):
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(r"""
@string{jmlr = "JMLR"}
@article{test2024,
  title={Test},
  author={A, B},
  journal=jmlr,
  year={2024}
}
""", encoding="utf-8")
        entries = parse_bib_file(bib_file)
        assert len(entries) == 1
        assert entries[0].venue == "JMLR"


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_nested_braces_in_value(self):
        entries = parse_bib_text(r"""
@article{test2024,
  title={A \textit{nested} \textbf{title} test},
  author={Doe, John},
  year={2024}
}
""")
        assert len(entries) == 1
        assert "nested" in entries[0].title
        assert "title" in entries[0].title

    def test_empty_fields_text(self):
        """Entry with key only, no fields."""
        entries = parse_bib_text(r"@misc{justakey}")
        assert len(entries) == 1
        assert entries[0].key == "justakey"

    def test_entry_with_minimal_fields(self):
        entries = parse_bib_text(r"@article{minimal, title={Only Title}, author={One, Author}, year={2024}}")
        assert len(entries) == 1
        assert entries[0].title == "Only Title"

    def test_mixed_delimiter_fields(self):
        """Some fields use {}, others use ""."""
        entries = parse_bib_text(r"""
@article{mixed2024,
  title={Braced Title},
  author="Quoted, Author",
  year="2024"
}
""")
        assert len(entries) == 1
        assert entries[0].title == "Braced Title"
        assert entries[0].authors == ["Quoted, Author"]
        assert entries[0].year == 2024

    def test_raw_text_preserved(self):
        entries = parse_bib_text(r"@article{test, title={T}, author={A, B}, year={2024}}")
        assert len(entries) == 1
        assert entries[0].raw_text.startswith("@article")
        assert entries[0].raw_text.endswith("}")

    def test_unknown_entry_type_still_parsed(self):
        """Entries with non-standard types are still parsed."""
        entries = parse_bib_text(r"""
@techreport{tr2024,
  title={Technical Report},
  author={Engineer, Chief},
  institution={MIT},
  year={2024}
}
""")
        assert len(entries) == 1
        assert entries[0].entry_type == "techreport"
        assert entries[0].title == "Technical Report"
