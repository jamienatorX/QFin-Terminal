"""Provider-independent policy for user-facing QFin finance answers."""

from __future__ import annotations

import re
from collections.abc import Sequence


OPENING_HEADINGS = {
    "company": "Investment view",
    "comparison": "Bottom line",
    "news": "Market read",
    "headlines": "Market read",
    "finance_concept": "In plain English",
    "document_analysis": "Executive summary",
}

KNOWN_HEADINGS = (
    "Investment view|Business and growth|Profitability and cash flow|"
    "Balance sheet and valuation|Key risks|Verdict|Bottom line|Side-by-side|"
    "What decides it|Market read|What happened|Why it matters|Watch next|"
    "In plain English|How it works|Formula|Example|How to use it|Executive summary|"
    "Performance|Financial position|Investor takeaways|Key changes|Financial trends|"
    "Interpretation|Profitability|Historical context|Financial health|Valuation and market signal|"
    "Key risks and watch items|Coverage gap|Attachment received and parsed|Key extracted disclosures|"
    "Data limitations|Methodology|Caveat"
)

GENERIC_VERDICT_PATTERNS = (
    r"Use the valuation, growth, profitability, cash-flow, and leverage measures together; "
    r"no single metric is a complete investment verdict\.\s*",
    r"A stronger investment call would require comparing these figures against multi-year growth, "
    r"segment margins, free-cash-flow durability, and peers\.\s*",
    r"No single metric is a complete investment verdict\.\s*",
)

INTERNAL_DIAGNOSTIC_PATTERNS = (
    r"Model answer mentioned extra ticker-like symbols outside the requested scope:[^\n]*\.??",
    r"Deterministic finance guidance was used to keep the response grounded and time-bounded\.??",
    r"Finance narrative fallback:[^\n]*",
)


def _clean_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _normalize_user_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def user_requests_methodology(query: str) -> bool:
    normalized = _normalize_user_text(query)
    if any(
        phrase in normalized
        for phrase in (
            "methodology",
            "where did you get",
            "where do you get",
            "how did you get",
            "how do you get",
            "data source",
            "data sources",
        )
    ):
        return True
    return bool(
        re.search(r"\b(?:cite|show|list|provide|share)\s+(?:your\s+)?sources?\b", normalized)
        or re.search(r"\b(?:what|which)\s+sources?\s+(?:did|do|are|were)\b", normalized)
        or re.search(r"\bsource\s+of\s+(?:the|this|your)\s+data\b", normalized)
    )


def _remove_methodology(content: str, preserve_methodology: bool) -> str:
    if preserve_methodology:
        return content
    return re.sub(
        r"(?ims)(?:\A|\n{2})(?:#{1,6}\s+|\*\*)?Methodology(?:\*\*)?\s*:?\s*"
        r"(?:\n|$).*?(?=\n{2}(?:#{1,6}\s+\S[^\n]*|\*\*[^*\n]+\*\*\s*:?)|\Z)",
        "\n",
        content,
    ).strip()


def _canonicalize_data_limitation_headings(content: str) -> str:
    return re.sub(
        r"(?mi)^\s*#{1,6}\s+(?:Caveat|Coverage gaps?|Data gaps?|Limitations?|Data limitations)\s*$",
        "## Data limitations",
        content,
    )


def _extract_data_limitations(content: str) -> tuple[str, list[str]]:
    canonical = _canonicalize_data_limitation_headings(content)
    section_pattern = re.compile(
        r"(?ims)^## Data limitations\s*\n+(.*?)(?=^##\s+\S|\Z)"
    )
    items: list[str] = []

    for match in section_pattern.finditer(canonical):
        current: list[str] = []

        def flush_current() -> None:
            if current:
                item = " ".join(current).strip()
                if item:
                    items.append(item)
                current.clear()

        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line:
                flush_current()
                continue
            bullet = re.match(r"^[-*]\s+(.*)$", line)
            if bullet:
                flush_current()
                current.append(bullet.group(1).strip())
            else:
                current.append(line)
        flush_current()

    remaining = section_pattern.sub("", canonical)
    remaining = re.sub(r"\n{3,}", "\n\n", remaining).strip()
    return remaining, items


def _consolidate_data_limitations(
    content: str,
    extra_gaps: Sequence[str] = (),
) -> str:
    remaining, existing_items = _extract_data_limitations(content)
    candidates = [*existing_items, *(str(gap).strip() for gap in extra_gaps if gap)]
    unique_items: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = re.sub(r"\s+", " ", item).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique_items.append(cleaned)
    if not unique_items:
        return remaining
    gap_block = "\n".join(f"- {item}" for item in unique_items)
    return f"{remaining}\n\n## Data limitations\n\n{gap_block}".strip()


def _remove_internal_diagnostics(content: str) -> str:
    cleaned = content
    for pattern in INTERNAL_DIAGNOSTIC_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)

    # Remove a now-empty provider-generated caveat block rather than showing an
    # implementation heading to the user.
    cleaned = re.sub(
        r"(?ims)(?:\A|\n{2})(?:#{1,6}\s+|\*\*)?Caveat(?:\*\*)?\s*:?\s*"
        r"(?:\n|$)\s*(?=(?:\n{2}(?:#{1,6}\s+|\*\*)[A-Z])|\Z)",
        "\n",
        cleaned,
    )
    return cleaned.strip()


def _remove_generic_verdict_boilerplate(content: str) -> str:
    cleaned = content
    for pattern in GENERIC_VERDICT_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"(?mi)^\s*(?:##|\*\*)\s*Verdict\*?\*?\s*$\n(?=\s*(?:##|\Z))",
        "",
        cleaned,
    )
    return cleaned.strip()


def _opening_heading(route_kind: str) -> str:
    return OPENING_HEADINGS.get(route_kind, "Answer")


def normalize_finance_answer(
    content: str,
    route_kind: str,
    preserve_methodology: bool = False,
) -> str:
    """Return stable QFin Markdown without changing supplied financial claims."""
    normalized = _clean_text(content)
    normalized = _remove_methodology(normalized, preserve_methodology)
    normalized = _remove_internal_diagnostics(normalized)
    normalized = _remove_generic_verdict_boilerplate(normalized)

    opening_heading = _opening_heading(route_kind)
    if not normalized:
        return (
            f"## {opening_heading}\n\n"
            "Reliable analysis could not be produced from the available evidence."
        )

    normalized = re.sub(
        r"\A\s*(?:(?:#{1,6}\s+)?Q(?=\s*(?::|-|\n|$))|\*\*Q\*\*)\s*[:\-]?\s*",
        "",
        normalized,
        flags=re.I,
    )

    opening_labels = "Direct answer|Answer"
    if route_kind == "document_analysis":
        opening_labels += "|Attachment analysis|Financial statement analysis"
    normalized = re.sub(
        rf"\A\s*#{{1,6}}\s+(?:{opening_labels})\s*(?:[:\-]\s*)?(?:\n+|$)",
        f"## {opening_heading}\n\n",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        rf"\A\s*(?:\*\*(?:{opening_labels})\*\*|(?:{opening_labels})\b)\s*[:\-]?\s*",
        f"## {opening_heading}\n\n",
        normalized,
        flags=re.I,
    )

    normalized = re.sub(
        rf"(?m)^\*\*({KNOWN_HEADINGS})\*\*\s*$",
        r"## \1",
        normalized,
        flags=re.I,
    )
    normalized = _canonicalize_data_limitation_headings(normalized)
    normalized = re.sub(r"(?m)([^\n])\n(##\s+)", r"\1\n\n\2", normalized)
    normalized = re.sub(r"(?m)^(##\s+[^\n]+)\n(?!\n)", r"\1\n\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    normalized = _consolidate_data_limitations(normalized)

    structured_routes = {
        "company",
        "comparison",
        "news",
        "headlines",
        "finance_concept",
        "document_analysis",
    }
    if route_kind in structured_routes and not normalized.startswith("## "):
        normalized = f"## {opening_heading}\n\n{normalized}"
    return normalized


def finalize_finance_answer(
    content: str,
    missing_data: Sequence[str] = (),
    preserve_methodology: bool = False,
) -> str:
    """Apply final disclosure policy and append genuine data gaps once."""
    finalized = _remove_methodology(_clean_text(content), preserve_methodology)
    finalized = _remove_internal_diagnostics(finalized)
    finalized = _remove_generic_verdict_boilerplate(finalized)

    return _consolidate_data_limitations(finalized, missing_data)
