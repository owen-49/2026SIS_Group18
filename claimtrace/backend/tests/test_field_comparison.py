"""Author and venue comparison used by the bibliography audit."""

from backend.src.services.field_comparison import (
    compare_authors,
    decode_latex,
    same_person,
)

VIT_RECORD = [
    "Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov", "Dirk Weissenborn",
    "Xiaohua Zhai", "Thomas Unterthiner", "Mostafa Dehghani", "Matthias Minderer",
    "Georg Heigold", "Sylvain Gelly", "Jakob Uszkoreit", "Neil Houlsby",
]
VIT_BIB = [
    "Dosovitskiy, Alexey", "Beyer, Lucas", "Kolesnikov, Alexander", "Weissenborn, Dirk",
    "Zhai, Xiaohua", "Unterthiner, Thomas", "Dehghani, Mostafa", "Minderer, Matthias",
    "Heigold, Georg", "Gelly, Sylvain", "others",
]


def test_decode_latex_accents():
    assert decode_latex(r"Tram{\`e}r") == "Tramèr"
    assert decode_latex(r"G{\"o}del") == "Gödel"
    assert decode_latex(r"\'{E}cole") == "École"
    assert decode_latex(r"{\o}stergaard") == "østergaard"


def test_same_person_tolerates_spelling_of_one_name():
    assert same_person(r"Tram{\`e}r, Florian", "Florian Tramèr")
    assert same_person("Madry, Aleksander", "Aleksander Mądry")
    assert same_person("Ghaffari Laleh, Narmin", "Narmin Ghaffari Laleh")
    assert same_person("van Treeck, Marko", "Marko van Treeck")
    assert same_person("Shlens, Jon", "Jonathon Shlens")
    assert same_person("Goodfellow, Ian J", "Ian Goodfellow")
    assert same_person("McDaniel, Patrick", "Patrick Drew McDaniel")


def test_same_person_refuses_different_people():
    assert not same_person("Smith, Jane", "John Smith")
    assert not same_person("Chen, Hongyang", "Huaming Chen")
    assert not same_person("Zhang, Jianping", "Jiayu Wang")


def test_truncated_author_list_is_reported_with_missing_names():
    result = compare_authors(VIT_BIB, VIT_RECORD)
    assert result.status == "MISMATCH"
    assert "10 of the 12" in result.detail
    assert "Jakob Uszkoreit, Neil Houlsby" in result.detail


def test_and_others_that_leaves_nobody_out_is_a_match():
    assert compare_authors(VIT_BIB, VIT_RECORD[:10]).status == "MATCH"


def test_complete_list_matches_and_order_matters():
    bib = [name for name in VIT_BIB if name != "others"] + ["Uszkoreit, Jakob", "Houlsby, Neil"]
    assert compare_authors(bib, VIT_RECORD).status == "MATCH"
    swapped = [bib[1], bib[0], *bib[2:]]
    result = compare_authors(swapped, VIT_RECORD)
    assert result.status == "MISMATCH"
    assert "Author 1 differs" in result.detail


def test_missing_and_extra_authors_without_others():
    assert compare_authors(["Dosovitskiy, Alexey"], VIT_RECORD[:2]).status == "MISMATCH"
    result = compare_authors(["Dosovitskiy, Alexey", "Beyer, Lucas"], VIT_RECORD[:1])
    assert result.status == "MISMATCH"
    assert "Not in the record: Beyer, Lucas" in result.detail


def test_no_comparison_when_a_side_is_empty():
    assert compare_authors([], VIT_RECORD) is None
    assert compare_authors(["others"], VIT_RECORD) is None
    assert compare_authors(VIT_BIB, []) is None



def test_given_name_conflict_is_shown_but_not_decisive():
    result = compare_authors(["Smith, Jane"], ["John Smith"])
    assert result.status == "MISMATCH"
    assert result.decisive is False
    assert "same surname but a different given name" in result.detail
