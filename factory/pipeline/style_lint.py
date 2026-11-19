#!/usr/bin/env python3
"""Deterministic style gate for instruction.md (CUA-Gym delegation style).

    style_lint.py <instruction.md>...     exit 1 and list problems if any

The instruction must read like a person handing off work: one or two plain
paragraphs, no markdown structure, no tool how-to, no assistant-speak. The
LLM stylist does the rewriting; this only catches what is mechanically wrong.
"""

import re
import sys
from pathlib import Path

RULES = [
    (r"^\s*#", "markdown heading"),
    (r"^\s*([-*•]|\d+[.)])\s", "bullet or numbered list"),
    (r"\*\*|__", "bold text"),
    (r"\bbrowser\s+(command|tool)|--help|\bMCP\b|screenshot|coordinates?\b", "explains the browser tooling"),
    (r"\b(ensure|make sure|please note|note that|be sure to|it is important|carefully|thoroughly|double-check)\b", "assistant-speak"),
    (r"\b(your task is|you are (an?|the) (ai|assistant|agent))\b", "addresses the model as a model"),
    (r"\b(step \d|first,|second,|finally,)", "step-by-step procedure"),
    (r"\b(verifier|reward|graded|grading|rubric|checkpoint)\b", "leaks evaluation"),
    (r"\b(trap|tricky|misleading|distractor)\b", "announces the trap"),
    (r"[\U0001F300-\U0001FAFF]", "emoji"),
]
MAX_PARAGRAPHS = 2
MAX_WORDS = 320


def lint(text: str):
    problems = []
    for pattern, why in RULES:
        for line in text.splitlines():
            if re.search(pattern, line, re.I):
                problems.append(f"{why}: {line.strip()[:90]}")
                break
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paragraphs) > MAX_PARAGRAPHS:
        problems.append(f"{len(paragraphs)} paragraphs (max {MAX_PARAGRAPHS})")
    words = len(text.split())
    if words > MAX_WORDS:
        problems.append(f"{words} words (max {MAX_WORDS})")
    return problems


def main():
    failed = 0
    for path in sys.argv[1:]:
        problems = lint(Path(path).read_text())
        for p in problems:
            print(f"{path}: {p}")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
