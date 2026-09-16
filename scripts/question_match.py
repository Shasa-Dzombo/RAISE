"""Match inbound question text against question_bank.question.

Simple, explainable token-overlap matching -- no embeddings yet (no provider
configured). question_bank.embedding stays untouched and ready for a later
semantic-match upgrade with zero schema change.

Uses the overlap coefficient (|A n B| / min(|A|, |B|)), not Jaccard: a real
inbound email carries a lot of padding around the actual question (greeting,
small talk, sign-off), which dilutes Jaccard's union-based denominator far
below any usable threshold even for an exact question match. The overlap
coefficient normalizes against the shorter set (almost always the terse
question_bank phrasing), so a fully-contained question scores high
regardless of how much other text surrounds it in the real message.

A pure score threshold still lets one generic shared word (e.g. "current")
falsely qualify a two-token question like "current runway" -- so a match
also needs a minimum absolute overlap count, not just a high ratio.
"""

import re

WORD_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "you", "your", "what",
    "how", "when", "where", "which", "who", "and", "or", "to", "of", "in",
    "on", "for", "with", "this", "that", "it", "please", "can", "could",
    "would", "i", "we", "our", "us", "will", "be", "have", "has", "any",
}
MIN_OVERLAP_COUNT = 2


def tokenize(text):
    words = WORD_RE.findall(text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def _score(inbound_tokens, q_tokens):
    overlap = inbound_tokens & q_tokens
    smaller = min(len(inbound_tokens), len(q_tokens))
    if smaller == 0:
        return 0.0, overlap
    required_overlap = min(MIN_OVERLAP_COUNT, len(q_tokens))
    if len(overlap) < required_overlap:
        return 0.0, overlap
    return len(overlap) / smaller, overlap


def best_match(inbound_text, questions, threshold=0.5):
    """questions: list of (id, question_text). Returns (id, question_text, score) or None."""
    matches = all_matches(inbound_text, questions, threshold)
    return matches[0] if matches else None


def all_matches(inbound_text, questions, threshold=0.5):
    """Every question above threshold, sorted by score descending -- a real
    email can ask more than one question at once."""
    inbound_tokens = tokenize(inbound_text)
    if not inbound_tokens:
        return []

    matches = []
    for qid, question_text in questions:
        q_tokens = tokenize(question_text)
        if not q_tokens:
            continue
        score, _overlap = _score(inbound_tokens, q_tokens)
        if score >= threshold:
            matches.append((qid, question_text, score))

    matches.sort(key=lambda m: m[2], reverse=True)
    return matches
