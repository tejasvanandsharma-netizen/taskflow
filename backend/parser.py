"""TaskFlow Section 3: deterministic, keyless mock parser for quick-add.

Runs with zero API keys and zero network calls. An optional real-LLM path can
be enabled with the USE_REAL_LLM environment flag (defaults to off).
"""

import os
import re

PRIORITY_KEYWORDS = ["urgent", "asap", "whenever", "low priority"]

DUE_DATE_PHRASES = [
    "today",
    "tomorrow",
    "next week",
    "next monday", "next tuesday", "next wednesday", "next thursday",
    "next friday", "next saturday", "next sunday",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]

DEFAULT_TITLE = "Untitled task"

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "0") == "1"


def _parse_priority(description):
    """Priority: urgent/asap win over whenever/low-priority; default medium."""
    lower = description.lower()
    if "urgent" in lower or "asap" in lower:
        return "high"
    if "whenever" in lower or "low priority" in lower:
        return "low"
    return "medium"


def _parse_due_date_hint(description):
    """First due-date phrase found, checked in spec order."""
    lower = description.lower()
    for phrase in DUE_DATE_PHRASES:
        if phrase in lower:
            return phrase
    return None


def _strip_keywords(title, due_date_hint):
    """Remove every priority keyword and the matched date phrase (all occurrences)."""
    phrases = list(PRIORITY_KEYWORDS)
    if due_date_hint:
        phrases.append(due_date_hint)
    for phrase in phrases:
        title = re.sub(re.escape(phrase), "", title, flags=re.IGNORECASE)
    return title.strip()


def parse_quick_add(description):
    """Parse free text into a task record dict.

    Returns {"title", "priority", "due_date_hint"}. Whitespace handling is
    intentional: spaces left behind by keyword removal are preserved.
    """
    priority = _parse_priority(description)
    due_date_hint = _parse_due_date_hint(description)
    title = _strip_keywords(description, due_date_hint) or DEFAULT_TITLE
    return {"title": title, "priority": priority, "due_date_hint": due_date_hint}


SYSTEM_PROMPT = (
    "You are TaskFlow's quick-add assistant. Convert the user's plain-English "
    "task description into a single JSON object with exactly these fields: "
    '"title" (the remaining text after priority and due-date words are removed, '
    'or "Untitled task" if empty), "priority" (one of "low", "medium", "high"), '
    'and "due_date_hint" (a string like "tomorrow" or "next friday", or null).'
)


def build_prompt(description):
    """Role-based prompt structure: a system instruction plus a user message."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": description},
    ]
