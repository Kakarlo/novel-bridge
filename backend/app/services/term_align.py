"""EXPERIMENTAL — deterministic source-term -> English-name alignment (no LLM).

The problem: a glossary entry becomes authoritative only once it has BOTH the English
``surface_form`` and the original ``source_term`` (the prompt then tells the model to render
that exact source term as that exact English). Users know the English name (references are
English) but not the source term, so pairing is tedious. This proposes the pairings.

The approach — and what it deliberately is NOT:
- NOT a translation or transliteration. "林尘" has many valid romanizations; the translator
  CHOSE one ("Lin Chen" / "Rin Jin" / an invented spelling). A dictionary/pinyin library
  can't know which, and string similarity between the source glyphs and the English is ~0.
- Instead: the source chapter and its translation tell the SAME story in the SAME order, so a
  name's ROLE lines up even when its spelling doesn't. We correlate each source proper noun's
  (first-appearance rank, frequency) with each English name's (first-appearance rank,
  frequency). The character who appears 1st and 12x in the source is almost certainly the one
  who appears 1st and 12x in the translation.

Output is a ranked list of PROPOSALS with a confidence and a human-readable basis. It never
writes the glossary — the user confirms a pair, which sets ``source_term`` through the normal
glossary write. Experimental and offline; gated with the source-term NER feature.

ponytail: appearance-rank + frequency is a heuristic with a known ceiling — it blurs when
many names share a frequency, when a name is pronoun-dropped in one text but not the other,
or when several names are introduced in a burst. That's exactly why it's a confirm-first
proposal, not an auto-write. Upgrade path if too noisy in practice: a single narrow LLM
alignment call behind the engine interface (a documented future track, not this module).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import AlignmentCandidate, GlossaryEntry
from app.services.term_match import _build_pattern


@dataclass
class _Occurrence:
    """A term with where it first appears and how often, within one text."""

    text: str
    first_pos: int
    count: int


def _source_occurrences(source_terms: list[str], raw_text: str) -> list[_Occurrence]:
    """First-appearance position + count for each source term in ``raw_text``.

    CJK has no word boundaries, so a plain substring scan is the correct tool (whole-word
    regex boundaries are meaningless here). Terms that don't actually appear are dropped.
    """
    occ: list[_Occurrence] = []
    for term in source_terms:
        pos = raw_text.find(term)
        if pos < 0:
            continue
        occ.append(_Occurrence(term, pos, raw_text.count(term)))
    return occ


def _english_occurrences(
    glossary: list[GlossaryEntry], output_text: str
) -> list[_Occurrence]:
    """First-appearance position + count for each glossary English name in ``output_text``.

    Reuses term_match's whole-word, case-insensitive pattern so "Lin" doesn't match inside
    "Linda" — consistent with the in-context review detector. Names that don't appear, or
    that already have a source_term (nothing to align), are skipped.
    """
    occ: list[_Occurrence] = []
    seen: set[str] = set()
    for entry in glossary:
        if entry.source_term:  # already paired — no alignment needed
            continue
        key = entry.surface_form.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        pattern = _build_pattern(entry.surface_form)
        if pattern is None:
            continue
        matches = list(pattern.finditer(output_text))
        if not matches:
            continue
        occ.append(_Occurrence(entry.surface_form, matches[0].start(), len(matches)))
    return occ


def _rank_map(occ: list[_Occurrence]) -> dict[str, int]:
    """Map each term to its appearance-order rank (0 = appears first)."""
    ordered = sorted(occ, key=lambda o: o.first_pos)
    return {o.text: i for i, o in enumerate(ordered)}


def _confidence(src: _Occurrence, eng: _Occurrence, rank_gap: int, n: int) -> float:
    """Score a candidate pair in 0..1 from rank agreement + frequency agreement.

    - Rank agreement: 1.0 when the two share the same appearance rank, decaying with the gap
      (normalized by how many terms there are, so a 1-rank gap matters more in a small cast).
    - Frequency agreement: ratio of the smaller count to the larger (1.0 == identical counts).
    The two are averaged. Deterministic; no magic thresholds beyond this blend.
    """
    rank_score = max(0.0, 1.0 - (rank_gap / n)) if n > 0 else 0.0
    lo, hi = sorted((src.count, eng.count))
    freq_score = (lo / hi) if hi > 0 else 0.0
    return round((rank_score + freq_score) / 2, 3)


def align_terms(
    source_terms: list[str], glossary: list[GlossaryEntry], raw_text: str, output_text: str
) -> list[AlignmentCandidate]:
    """Propose source-term -> English-name pairings, highest confidence first.

    Deterministic and offline. ``source_terms`` is the output of the source-term NER pass;
    the English side is the project's unpaired glossary names found in ``output_text``.
    Greedy 1:1 matching by appearance rank (closest rank wins), frequency corroborating the
    confidence. A PROPOSAL list only — never writes the glossary.
    """
    src_occ = _source_occurrences(source_terms, raw_text)
    eng_occ = _english_occurrences(glossary, output_text)
    if not src_occ or not eng_occ:
        return []

    src_rank = _rank_map(src_occ)
    eng_rank = _rank_map(eng_occ)
    n = max(len(src_occ), len(eng_occ))

    # Greedy 1:1 by smallest rank gap, so each source term and each English name is used at
    # most once. Build all (gap, src, eng) triples, sort, then take non-conflicting pairs.
    triples: list[tuple[int, _Occurrence, _Occurrence]] = []
    for s in src_occ:
        for e in eng_occ:
            gap = abs(src_rank[s.text] - eng_rank[e.text])
            triples.append((gap, s, e))
    triples.sort(key=lambda t: (t[0], -min(t[1].count, t[2].count)))

    used_src: set[str] = set()
    used_eng: set[str] = set()
    candidates: list[AlignmentCandidate] = []
    for gap, s, e in triples:
        if s.text in used_src or e.text in used_eng:
            continue
        used_src.add(s.text)
        used_eng.add(e.text)
        candidates.append(
            AlignmentCandidate(
                source_term=s.text,
                surface_form=e.text,
                source_count=s.count,
                english_count=e.count,
                confidence=_confidence(s, e, gap, n),
                basis="appearance-order + frequency",
            )
        )

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates
