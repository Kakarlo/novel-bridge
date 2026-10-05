"""EXPERIMENTAL — deterministic source-language proper-noun detection (zh/ja).

Goal: lessen the AI's load. The English name detector (``noun_extract``) already finds
English surface forms in references; this is its mirror for the SOURCE text — it extracts
Chinese/Japanese proper nouns via spaCy's language-specific NER so a translator (or a later
alignment step) has candidate source terms without asking the LLM.

Status: experimental and OPTIONAL. It is OFF unless ``NB_SOURCE_TERMS=true`` AND the
relevant spaCy model is installed:
  - Chinese: ``python -m spacy download zh_core_web_sm``   (~48MB)
  - Japanese: ``python -m spacy download ja_core_news_sm`` (~40MB)
If a model is missing it degrades to an empty list (never raises), so nothing breaks.

CHEAP TO REMOVE: this whole file + the one ``extract_source_terms`` call site + the
``NB_SOURCE_TERMS`` flag. No schema change, no new storage. Delete and it's gone.

Caveats (acceptable while experimental): Chinese has no spaces, so the small model is only
fair on invented xianxia terms; it is decent on modern person/place names. This yields a
list of source terms, NOT alignment to English — pairing is a separate (harder) step.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# One spaCy model per source language. NER labels differ slightly by model; we keep the
# person/place/org-like ones. zh/ja core models use PERSON/GPE/LOC/ORG/FAC/NORP/EVENT etc.
_MODEL_BY_LANG = {"zh": "zh_core_web_sm", "ja": "ja_core_news_sm"}
_NAME_LABELS = {"PERSON", "ORG", "GPE", "LOC", "FAC", "NORP", "EVENT", "PRODUCT", "WORK_OF_ART"}

# Cache: lang -> loaded pipeline, or False if load failed (so we try once).
_nlp_cache: dict[str, object | None] = {}


def _get_nlp(lang: str):
    """Load (once) the spaCy pipeline for ``lang``, or return None if unavailable."""
    if lang in _nlp_cache:
        cached = _nlp_cache[lang]
        return None if cached is False else cached
    model = _MODEL_BY_LANG.get(lang)
    if not model:
        _nlp_cache[lang] = False
        return None
    try:
        import spacy

        nlp = spacy.load(model, exclude=["lemmatizer", "attribute_ruler"])
        _nlp_cache[lang] = nlp
        return nlp
    except Exception as exc:  # ImportError / model-not-found / load error
        _nlp_cache[lang] = False
        logger.warning(
            "Source-term NER unavailable for lang=%s (%s); returning no source terms. "
            "Install with: python -m spacy download %s",
            lang,
            exc,
            model,
        )
        return None


def extract_source_terms(text: str, source_lang: str, *, limit: int = 30) -> list[str]:
    """Return likely source-language proper nouns in ``text``, most frequent first.

    Offline and deterministic. Empty list if the model for ``source_lang`` isn't installed
    or the language is unsupported — callers must treat an empty result as "unavailable",
    not "none found", when the feature is relevant.
    """
    if not text or not text.strip():
        return []
    nlp = _get_nlp(source_lang)
    if nlp is None:
        return []
    doc = nlp(text)

    from collections import Counter

    counts: Counter[str] = Counter()
    for ent in doc.ents:
        if ent.label_ not in _NAME_LABELS:
            continue
        term = ent.text.strip()
        # Drop single CJK characters (usually too generic to be a useful term) and empties.
        if len(term) <= 1:
            continue
        counts[term] += 1

    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [term for term, _ in ordered[:limit]]
