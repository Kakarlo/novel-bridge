"""Translation engine interface and shared data classes (Requirement 5.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.models import GlossaryEntry, SourceLang


@dataclass
class TranslationRequest:
    raw_text: str
    source_lang: SourceLang
    glossary: list[GlossaryEntry] = field(default_factory=list)
    reference_context: str = ""
    model: str | None = None
    # Per-project writing-style profile (task 3). Injected into the translation prompt to
    # anchor register/tone/terminology across the series. Empty when the project has none.
    style_profile: str = ""


@dataclass
class TranslationChunk:
    content: str
    done: bool = False
    meta: dict | None = None


@dataclass
class ReferenceExtraction:
    """Result of distilling a reference chapter into reusable, non-echoable context.

    `summary` captures plot/style/tone in a few sentences; `candidate_terms` lists
    recurring proper nouns / terminology worth adding to the glossary. Both are kept
    small so they can be injected into the translate prompt without the model echoing
    raw reference text (the reference-echo bug this fixes).
    """

    summary: str
    candidate_terms: list[str] = field(default_factory=list)


@dataclass
class GlossaryPair:
    """One LLM-paired glossary candidate: a source term bound to its English spelling.

    This is the replacement for the old deterministic appearance-rank/frequency aligner
    (``services/term_align.py``). That heuristic pairing produced near-random results
    because the signal it used (where/how often a name appears) does not survive
    translation reliably — users couldn't validate the output.

    The LLM does the correlation instead: given the raw source chapter and its English
    translation (which share the SAME story and the translator's ACTUAL chosen spellings),
    it binds each source term to the exact English form that appears in the translation.
    It never invents a new romanization; ``surface_form`` is the spelling already in the
    output. Rows land as ``candidate`` glossary entries for the user to approve.

    - ``category``/``gender`` mirror the glossary model (``character|title|term``; gender
      is meaningful for characters and steers zh->en pronoun consistency).
    - ``note`` is a short optional disambiguator the model may add (e.g. "protagonist").
    """

    source_term: str
    surface_form: str
    category: str = "term"
    gender: str | None = None
    note: str | None = None


class TranslationEngine(ABC):
    """All engines conform to this streaming-first interface."""

    name: str = "base"

    @abstractmethod
    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        """Yield TranslationChunks; the final chunk has done=True."""
        raise NotImplementedError

    @abstractmethod
    async def extract_reference(
        self,
        content: str,
        source_lang: SourceLang,
        detected_names: list[str] | None = None,
    ) -> ReferenceExtraction:
        """Distill a reference chapter into a summary + candidate glossary terms.

        Runs once when a reference is uploaded (and on resummarize). The derived,
        compact result is what later translations consume instead of the raw text.
        ``detected_names`` are optional rule-based proper-noun hints (field-fix #2) the
        engine may use to anchor its extraction.
        """
        raise NotImplementedError

    @abstractmethod
    async def extract_glossary(
        self,
        raw_text: str,
        output_text: str,
        source_lang: SourceLang,
        candidates: list[str] | None = None,
        model: str | None = None,
    ) -> list[GlossaryPair]:
        """Pair source terms to the English spellings used in a translation.

        Replaces the deterministic aligner. Given a source chapter (``raw_text``) and its
        English ``output_text`` — same story, translator's real spellings — return paired
        ``GlossaryPair`` candidates for the user to approve.

        ``candidates`` is an optional deterministic pre-filter (source-language proper nouns
        from ``services.source_terms`` and/or English names from ``services.noun_extract``).
        Passing a short list keeps the prompt small and cheap (the project's token-saving
        strategy for weak local models) and anchors the model to real recurring terms; the
        engine may still surface pairs beyond the hints. When ``candidates`` is empty the
        engine extracts from the texts alone.

        ``model`` optionally overrides the engine's default model for THIS call only. Pairing
        names correctly is accuracy-sensitive, so callers may pass a stronger model here than
        they would use for bulk translation; omitted → the engine's configured default.

        Offline-safe: return ``[]`` (never raise) when the backend is unreachable or the
        response can't be parsed, so a flaky model degrades to "no suggestions".
        """
        raise NotImplementedError

    @abstractmethod
    async def extract_style(
        self,
        content: str,
        source_lang: SourceLang,
    ) -> str:
        """Analyze a reference chapter and extract a reusable writing-style profile.

        Unlike the summary extraction (which distills plot/terms), this focuses purely on
        HOW the text is written: register, sentence rhythm, vocabulary, dialogue conventions,
        honorific handling, narrative perspective, and localization preferences. The result
        is a compact prose guide that can be injected as-is into the translate system prompt
        to anchor tone and style across an entire series.

        Stored per-project (not per-reference) because each novel has one cohesive style.
        Multiple references accumulate into a richer profile; the caller merges or replaces.

        ``content`` is the full English text of a reference chapter (references are always
        English translations). ``source_lang`` indicates the original language for CJK-aware
        analysis (e.g. honorific handling, pronoun drift, naming conventions).

        Returns a markdown-formatted style guide (target: 150–300 words). Empty string on
        any failure (degraded, never raises).
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the engine is ready to serve requests."""
        raise NotImplementedError

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return the model names this engine can serve, for the model picker.

        Offline-safe: return ``[]`` (never raise) when the backend is unreachable, so a
        disconnected engine degrades to "no choices" rather than erroring the endpoint.
        """
        raise NotImplementedError
