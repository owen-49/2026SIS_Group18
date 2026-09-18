"""Tests for reference_text.py.

Every entry below is copied verbatim from a parsed reference list under
``backend/uploads/parsed/``, including the ``Ł ukasz`` spacing artifact the PDF
extractor produced and the ``ﬁ`` ligature. Those are the inputs the parser will
meet in production, so they are the inputs it is tested against.
"""

from engine.reference_text import parse_reference_text

# backend/uploads/parsed/f940bcbf-...references.json #1
_INVERTED = (
    "[1] Artem Babenko and Victor Lempitsky. The inverted multi-index. "
    "IEEE Transactions on Pattern Analysis and Machine Intelligence, 2014."
)

# f940bcbf #9 -- the ligature is in the source and must survive parsing.
_TRANSFORMER_XL = (
    "[9] Zihang Dai, Zhilin Yang, Yiming Yang, William W Cohen, Jaime Carbonell, "
    "Quoc V Le, and Ruslan Salakhutdinov. Transformer-xl: Attentive language models "
    "beyond a ﬁxed-length context. In Conference of the Association for "
    "Computational Linguistics, 2019."
)

# f940bcbf #32 -- the author list contains an initial, so the first period after
# "David" does not end it.
_MUJA = (
    "[32] Marius Muja and David G. Lowe. Scalable nearest neighbor algorithms for "
    "high dimensional data. IEEE Transactions on Pattern Analysis and Machine "
    "Intelligence, 2014."
)

# 92574678 #5 -- a DOI, a URL, a parenthesised volume, and a full date.
_WIKIPEDIA = (
    "[5] Danqi Chen, Adam Fisch, Jason Weston, and Antoine Bordes. Reading Wikipedia "
    "to Answer Open-Domain Questions. In Proceedings of the 55th Annual Meeting of the "
    "Association for Computational Linguistics (Volume 1: Long Papers), pages "
    "1870–1879, Vancouver, Canada, July 2017. Association for Computational "
    "Linguistics. doi: 10.18653/v1/P17-1171. "
    "URL https://www.aclweb.org/anthology/P17-1171."
)

# 92574678 #7 -- an arXiv entry with no venue name at all.
_MULTI_PARAGRAPH = (
    "[7] Christopher Clark and Matt Gardner. Simple and Effective Multi-Paragraph "
    "Reading Comprehension. arXiv:1710.10723 [cs], October 2017. "
    "URL http://arxiv.org/abs/1710.10723. arXiv: 1710.10723."
)

# 92574678 #58 -- seven editors sit between "In" and the venue, and the author
# list carries the PDF extractor's spacing artifact in "Ł ukasz".
_ATTENTION = (
    "[58] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, "
    "Aidan N Gomez, Ł ukasz Kaiser, and Illia Polosukhin. Attention is all you "
    "need. In I. Guyon, U. V. Luxburg, S. Bengio, H. Wallach, R. Fergus, "
    "S. Vishwanathan, and R. Garnett, editors, Advances in Neural Information "
    "Processing Systems 30, pages 5998–6008. Curran Associates, Inc., 2017. "
    "URL http://papers.nips.cc/paper/7181-attention-is-all-you-need.pdf."
)

# cdb78a91 #3 -- the year sits between the authors and the title.
_ICON = (
    "[3] Devamanyu Hazarika, Soujanya Poria, Rada Mihalcea, Erik Cambria, and Roger "
    "Zimmermann. 2018. Icon: Interactive conversational memory network for multimodal "
    "emotion detection. In Proceedings of the 2018 conference on empirical methods in "
    "natural language processing. 2594–2604."
)

# f940bcbf #30 and #31 -- the two records the year tolerance was measured against.
_K_SPARSE = (
    "[30] Alireza Makhzani and Brendan Frey. K-sparse autoencoders. "
    "In International Conference on Representation Learning, 2014."
)

_WINNER_TAKE_ALL = (
    "[31] Alireza Makhzani and Brendan J Frey. Winner-take-all autoencoders. "
    "In Advances in Neural Information Processing Systems, 2015."
)


def test_parses_a_journal_entry():
    query = parse_reference_text(_INVERTED)
    assert query.title == "The inverted multi-index"
    assert query.authors == ["Artem Babenko", "Victor Lempitsky"]
    assert query.year == 2014
    assert query.venue == "IEEE Transactions on Pattern Analysis and Machine Intelligence"
    assert query.doi == ""
    assert query.arxiv_id == ""


def test_parses_a_conference_entry():
    query = parse_reference_text(_K_SPARSE)
    assert query.title == "K-sparse autoencoders"
    assert query.authors == ["Alireza Makhzani", "Brendan Frey"]
    assert query.year == 2014
    assert query.venue == "International Conference on Representation Learning"


def test_parses_a_venue_with_no_in_prefix():
    query = parse_reference_text(_WINNER_TAKE_ALL)
    assert query.title == "Winner-take-all autoencoders"
    assert query.year == 2015
    assert query.venue == "Advances in Neural Information Processing Systems"


def test_an_initial_in_the_author_list_does_not_end_it():
    # Splitting naively at the first ". " would give an author named "Marius Muja
    # and David G" and a title of "Lowe".
    query = parse_reference_text(_MUJA)
    assert query.authors == ["Marius Muja", "David G. Lowe"]
    assert query.title == "Scalable nearest neighbor algorithms for high dimensional data"
    assert query.venue == "IEEE Transactions on Pattern Analysis and Machine Intelligence"
    assert query.year == 2014


def test_a_year_before_the_title_does_not_become_the_title():
    query = parse_reference_text(_ICON)
    assert query.year == 2018
    assert query.title == (
        "Icon: Interactive conversational memory network for multimodal emotion detection"
    )
    assert query.authors[0] == "Devamanyu Hazarika"
    assert query.authors[-1] == "Roger Zimmermann"
    assert query.venue == (
        "Proceedings of the 2018 conference on empirical methods in natural language processing"
    )


def test_ligature_and_spacing_artifacts_survive_parsing():
    query = parse_reference_text(_TRANSFORMER_XL)
    assert "ﬁxed-length" in query.title
    assert query.title.startswith("Transformer-xl: Attentive language models beyond")
    assert query.year == 2019
    assert query.venue == "Conference of the Association for Computational Linguistics"


def test_extracts_the_doi_and_stops_before_the_url():
    query = parse_reference_text(_WIKIPEDIA)
    assert query.doi == "10.18653/v1/p17-1171"
    assert query.arxiv_id == ""
    assert query.title == "Reading Wikipedia to Answer Open-Domain Questions"
    assert query.year == 2017
    assert query.authors == [
        "Danqi Chen",
        "Adam Fisch",
        "Jason Weston",
        "Antoine Bordes",
    ]


def test_the_pages_location_and_date_are_not_part_of_the_venue():
    query = parse_reference_text(_WIKIPEDIA)
    assert query.venue == (
        "Proceedings of the 55th Annual Meeting of the Association for Computational "
        "Linguistics (Volume 1: Long Papers)"
    )


def test_extracts_the_arxiv_identifier_and_leaves_the_venue_empty():
    # The venue position here holds "arXiv:1710.10723 [cs]". Keeping it would put
    # an identifier into the venue tie-break, so it is dropped instead.
    query = parse_reference_text(_MULTI_PARAGRAPH)
    assert query.arxiv_id == "1710.10723"
    assert query.doi == ""
    assert query.venue == ""
    assert query.title == "Simple and Effective Multi-Paragraph Reading Comprehension"
    assert query.year == 2017


def test_editors_between_in_and_the_venue_are_skipped():
    query = parse_reference_text(_ATTENTION)
    assert query.venue == "Advances in Neural Information Processing Systems 30"
    assert query.title == "Attention is all you need"
    assert query.year == 2017
    assert len(query.authors) == 8
    assert query.authors[0] == "Ashish Vaswani"
    assert query.authors[-1] == "Illia Polosukhin"


def test_a_doi_in_the_entry_does_not_supply_the_year():
    # The DOI's own digits contain "2014"; stripping identifier fragments keeps
    # them from being read as a date.
    query = parse_reference_text(
        "[1] A. Author. A title. Journal of Things. doi: 10.1109/TPAMI.2014.2361319."
    )
    assert query.doi == "10.1109/tpami.2014.2361319"
    assert query.year is None


def test_a_run_of_initials_does_not_end_the_author_list():
    # "O.K." is four characters, so a single-letter initial test misses it and
    # the title comes out as "Li". Found by running the parser over all 155
    # entries in the parsed reference lists.
    query = parse_reference_text(
        "[17] Jiatao Gu, Yong Wang, Kyunghyun Cho, and Victor O.K. Li. Search engine "
        "guided neural machine translation. In AAAI Conference on Artificial "
        "Intelligence, 2018."
    )
    assert query.authors[-1] == "Victor O.K. Li"
    assert query.title == "Search engine guided neural machine translation"
    assert query.venue == "AAAI Conference on Artificial Intelligence"


def test_et_al_does_not_become_the_first_author():
    query = parse_reference_text(
        "[6] Xin Li et al. 2024. Do LLMs Feel? Teaching Emotion Recognition with "
        "Prompts, Retrieval, and Curriculum Learning. In Proceedings of the AAAI "
        "Conference on Artificial Intelligence."
    )
    assert query.authors == ["Xin Li"]
    assert query.year == 2024


def test_a_question_mark_inside_a_title_does_not_end_it():
    # A period break exists later in the entry, so the "?" is read as part of
    # the title.
    query = parse_reference_text(
        "[6] Xin Li et al. 2024. Do LLMs Feel? Teaching Emotion Recognition with "
        "Prompts, Retrieval, and Curriculum Learning. In Proceedings of the AAAI "
        "Conference on Artificial Intelligence."
    )
    assert query.title == (
        "Do LLMs Feel? Teaching Emotion Recognition with Prompts, Retrieval, and "
        "Curriculum Learning"
    )
    assert query.venue == "Proceedings of the AAAI Conference on Artificial Intelligence"


def test_a_question_mark_ending_a_title_does_end_it():
    # No period break exists anywhere here, so the "?" is the only terminator
    # between the title and the venue.
    query = parse_reference_text(
        "[34] Bruno A. Olshausen and David J. Field. Sparse coding with an "
        "overcomplete basis set, a strategy employed by v1? Vision Research, 1997."
    )
    assert query.title == (
        "Sparse coding with an overcomplete basis set, a strategy employed by v1"
    )
    assert query.venue == "Vision Research"
    assert query.year == 1997


def test_a_year_after_a_title_with_no_period_is_stripped_from_it():
    query = parse_reference_text(
        "[36] Alec Radford, Jeff Wu, Rewon Child, David Luan, Dario Amodei, and Ilya "
        "Sutskever. Language models are unsupervised multitask learners, 2019."
    )
    assert query.title == "Language models are unsupervised multitask learners"
    assert query.year == 2019
    assert query.venue == ""


def test_a_title_that_genuinely_ends_in_a_year_is_left_alone():
    # Only a comma-joined year is stripped, so this cannot clip a real title.
    query = parse_reference_text("[1] A. Author. The state of AI in 2024. A Journal, 2024.")
    assert query.title == "The state of AI in 2024"
    assert query.year == 2024


def test_a_truncated_entry_yields_what_it_actually_contains():
    # These three are cut off in the source PDF. Reporting the absent year as
    # absent is the correct outcome; inventing one would not be.
    truncated = parse_reference_text(
        "[19] Kelvin Guu, Tatsunori B. Hashimoto, Yonatan Oren, and Percy Liang. "
        "Generating sentences by editing prototypes. Transactions of the Association "
        "for Computational Linguistics, 6:437–450,"
    )
    assert truncated.title == "Generating sentences by editing prototypes"
    assert truncated.year is None
    assert truncated.venue == "Transactions of the Association for Computational Linguistics"

    mid_authors = parse_reference_text(
        "[62] Shuohang Wang, Mo Yu, Xiaoxiao Guo, Zhiguo Wang, Tim Klinger, Wei Zhang, "
        "Shiyu Chang,"
    )
    assert mid_authors.title == ""
    assert mid_authors.year is None


def test_it_never_raises_on_malformed_input():
    for text in [
        "",
        "   ",
        ".",
        "[1]",
        "[1] .",
        "[1] A. Author.",
        "no marker at all",
        "[]",
        "[9] only. two. periods.",
        "\x00\x01",
        "1" * 5000,
    ]:
        assert isinstance(parse_reference_text(text), type(parse_reference_text("")))


def test_an_empty_entry_yields_an_empty_query():
    query = parse_reference_text("")
    assert query.title == ""
    assert query.authors == []
    assert query.year is None
    assert query.venue == ""
    assert query.doi == ""
    assert query.arxiv_id == ""
