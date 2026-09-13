"""Resolve a claim's citation reference to parsed source passages.

This bridges the gap between "this claim cites reference X" and "here are the
passages from X's paper that an LLM should read to judge the claim."

The resolver is deliberately storage-agnostic: the caller injects two
callables — ``locate`` (find the source paper for a citation key) and
``parse`` (parse a located source paper into passages). The engine therefore
depends on neither the backend's paper store nor the parser package.

Once the source is parsed, its passages are indexed with the engine's
``Retriever`` and semantically retrieved against the claim, producing
``RetrievalResult`` objects ready for ``Verifier.verify_with_retrieval``.
"""

from dataclasses import dataclass, field
from typing import Callable

from .retriever import RetrievalResult, Retriever


@dataclass
class SourcePaper:
    """A source paper located for a citation reference.

    ``locate`` returns this; it carries just enough identity for downstream
    parsing and reporting. Any extra fields the caller needs can live in
    ``metadata``.
    """

    source_id: str
    title: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ResolvedSource:
    """Outcome of resolving a citation reference to parsed source passages."""

    citation_key: str
    resolved: bool
    source_id: str | None = None
    title: str | None = None
    passages: list[str] = field(default_factory=list)
    retrieval: list[RetrievalResult] = field(default_factory=list)
    reason: str = ""  # populated when resolution or parsing falls short


class SourceResolver:
    """Turn a citation reference into parsed source passages.

    Args:
        locate: Given a citation key, return the matching ``SourcePaper`` or
            ``None`` when no source is available for that reference.
        parse: Given a located ``SourcePaper``, parse it into a list of
            passage strings (typically the parser package's paragraph output).
        retriever: Optional ``Retriever``. Defaults to a fresh instance.
    """

    def __init__(
        self,
        locate: Callable[[str], SourcePaper | None],
        parse: Callable[[SourcePaper], list[str]],
        retriever: Retriever | None = None,
    ) -> None:
        self._locate = locate
        self._parse = parse
        self._retriever = retriever or Retriever()

    def resolve(self, claim: str, citation_key: str, k: int = 5) -> ResolvedSource:
        """Resolve ``citation_key`` to parsed passages and retrieve evidence.

        Args:
            claim: The claim text being audited.
            citation_key: The reference identifier (BibTeX key, marker, etc.).
            k: Number of passages to retrieve for LLM verification.

        Returns:
            ``ResolvedSource`` with resolution status, source identity, and the
            retrieved evidence passages ranked by semantic similarity.
        """
        source = self._locate(citation_key)
        if source is None:
            return ResolvedSource(
                citation_key=citation_key,
                resolved=False,
                reason=f"No source paper located for reference '{citation_key}'.",
            )

        passages = self._parse(source)
        if not passages:
            return ResolvedSource(
                citation_key=citation_key,
                resolved=True,
                source_id=source.source_id,
                title=source.title,
                passages=[],
                reason="Source located but parsed with no passages.",
            )

        self._retriever.build_index(passages)
        retrieval = self._retriever.retrieve(claim, k=k)

        return ResolvedSource(
            citation_key=citation_key,
            resolved=True,
            source_id=source.source_id,
            title=source.title,
            passages=passages,
            retrieval=retrieval,
        )
