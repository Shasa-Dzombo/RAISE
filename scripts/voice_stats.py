"""Compute grounding statistics for the founder voice study from sent-mail bodies.

Reads a JSON array of plaintext message bodies on stdin (quoted-reply lines
are stripped first) and prints word/sentence-length stats plus the most
common opening lines and sign-offs. Grounds identity/VOICE.md in data rather
than impression alone.

Usage:
    python scripts/voice_stats.py < bodies.json
"""

import json
import re
import sys
from collections import Counter

QUOTE_LINE_RE = re.compile(r"^\s*>")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z']+")


def strip_quoted_reply(body):
    lines = []
    for line in body.splitlines():
        if QUOTE_LINE_RE.match(line):
            break
        if re.match(r"^\s*On .+ wrote:\s*$", line):
            break
        if re.match(r"^-{2,} ?On .+ wrote ?-{2,}", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def first_line(body):
    for line in body.splitlines():
        if line.strip():
            return line.strip().rstrip(",.")
    return ""


def last_lines(body, n=3):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    return lines[-n:] if lines else []


def main():
    bodies = json.load(sys.stdin)
    clean_bodies = [strip_quoted_reply(b) for b in bodies if strip_quoted_reply(b)]

    word_counts = []
    sentence_lengths = []
    greetings = Counter()
    signoffs = Counter()

    for body in clean_bodies:
        words = WORD_RE.findall(body)
        word_counts.append(len(words))

        sentences = [s for s in SENTENCE_SPLIT_RE.split(body.replace("\n", " ")) if s.strip()]
        for s in sentences:
            sw = WORD_RE.findall(s)
            if sw:
                sentence_lengths.append(len(sw))

        greetings[first_line(body)] += 1
        for line in last_lines(body):
            if re.match(r"^(regards|best regards|kind regards|warm regards|thanks|cheers)\b", line, re.I):
                signoffs[line] += 1

    n = len(clean_bodies)
    avg_words = sum(word_counts) / n if n else 0
    avg_sentence_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0

    print("Messages analyzed: {}".format(n))
    print("Average message length: {:.1f} words".format(avg_words))
    print("Average sentence length: {:.1f} words".format(avg_sentence_len))
    print()
    print("Most common opening lines:")
    for line, count in greetings.most_common(10):
        print("  {}x  {!r}".format(count, line))
    print()
    print("Most common sign-offs:")
    for line, count in signoffs.most_common(10):
        print("  {}x  {!r}".format(count, line))


if __name__ == "__main__":
    main()
