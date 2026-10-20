"""Small text helpers: tokenising, safety-critical term extraction, recommendation splitting."""
from __future__ import annotations

import re
from typing import Iterable

STOPWORDS = frozenset("""
a an and are as at be been but by can could do does for from had has have he her his how i if in into is it its
may might more most my no not of on or our should so such than that the their them then there these they this to
too up us was we were what when which who will with would you your also any all each other some than very about
patient patients please advise recommend recommended recommendation take taking get use using given offer
""".split())

# Words that make a recommendation safety-critical (drugs, dosing). Matching is prefix-based so
# "antibiotics" matches "antibiotic".
DRUG_SUFFIXES = ("cillin", "mycin", "micin", "cycline", "floxacin", "azole", "olol", "pril", "sartan", "statin",
                 "profen", "fenac", "oxicam", "triptan", "parin", "dipine", "thiazide", "prazole", "tidine",
                 "setron", "azepam", "zolam", "codone", "xaban", "gliptin", "glutide", "sulfa",
                 "vir", "mab", "tinib", "ciclib", "gliflozin", "glitazone", "olone", "terol", "tropium")
DRUG_WORDS = frozenset("""
antibiotic antibiotics antimicrobial antimicrobials antiviral antivirals paracetamol acetaminophen aspirin ibuprofen
naproxen codeine morphine tramadol nitrofurantoin trimethoprim fosfomycin pivmecillinam amoxicillin doxycycline
clarithromycin erythromycin penicillin phenoxymethylpenicillin flucloxacillin cefalexin azithromycin
prednisolone prednisone dexamethasone steroid corticosteroid corticosteroids salbutamol bronchodilator mucolytic
metformin insulin warfarin heparin antihistamine decongestant opioid benzodiazepine antidepressant
""".split())
DOSE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|g|ml|iu|units?|%)\b|\b(?:once|twice|three times|four times)\s+(?:a\s+day|daily)\b|\b\d+\s?(?:days?|weeks?)\b", re.I)
NEGATION_CUES = ("do not", "don't", "should not", "must not", "not recommended", "not offer", "avoid", "never",
                 "not be offered", "not routinely", "no need", "unnecessary", "contraindicated")
ADVICE_VERBS = ("should", "recommend", "advise", "take ", "avoid", "use ", "see a", "see your", "consider", "rest",
                "drink", "stay ", "seek", "visit", "call", "get ", "apply", "start ", "stop ", "continue", "offer",
                "prescribe", "monitor", "return", "book", "make an appointment", "go to")

# A few clinically common abbreviations/lay terms expanded for lexical matching only.
SYNONYMS = {
    "uti": ["urinary", "tract", "infection", "cystitis"],
    "cystitis": ["urinary", "tract", "infection"],
    "cold": ["upper", "respiratory", "tract", "infection"],
    "flu": ["influenza", "respiratory"],
    "bronchitis": ["cough", "chest", "infection"],
    "cough": ["bronchitis"],
    "tonsillitis": ["sore", "throat"],
    "pharyngitis": ["sore", "throat"],
    "pee": ["urine"], "wee": ["urine"],
    "antibiotics": ["antimicrobial"], "antibiotic": ["antimicrobial"],
    "pregnant": ["pregnancy"],
}


def stem(word: str) -> str:
    w = word.lower()
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokenize(text: str, expand: bool = False) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    toks = [stem(t) for t in raw if t not in STOPWORDS and len(t) > 1]
    if expand:
        for t in list(raw):
            for extra in SYNONYMS.get(t, []):
                toks.append(stem(extra))
    return toks


def is_drug_term(word: str) -> bool:
    w = word.lower()
    return w in DRUG_WORDS or (len(w) > 6 and w.endswith(DRUG_SUFFIXES))


def critical_terms(text: str) -> list[str]:
    """Drug names and dose/duration expressions in `text` (lower-cased, de-duplicated, order kept)."""
    seen: dict[str, None] = {}
    for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text):
        if is_drug_term(w):
            seen[w.lower()] = None
    for m in DOSE_PATTERN.finditer(text):
        seen[re.sub(r"\s+", " ", m.group(0).lower())] = None
    return list(seen)


def term_in_text(term: str, text_lower: str) -> bool:
    """Prefix match for words ('antibiotic' in 'antibiotics'), exact match for dose expressions."""
    if re.search(r"\d", term):
        return re.sub(r"\s+", "", term) in re.sub(r"\s+", "", text_lower)
    return re.search(r"\b" + re.escape(term.rstrip("s")), text_lower) is not None


_REC_NUMBER = re.compile(r"(?m)^\s*\d+\.\d+(?:\.\d+)?\s+\S")
_TABLE_START = re.compile(r"(?mi)^\s*table\s+\d+\b")
_CHOICE_SECTION = re.compile(r"(?i)\b(first|second|alternative)[- ]?(line\s+)?choices?\b|\bchoice of antibiotic\b|\bdosing\b")


def is_recommendation(text: str, section: str = "") -> bool:
    """True for passages that state advice: numbered recommendations ('1.1.8 Do not offer ...') or
    prescribing tables ('First choice', 'Alternative choices').

    Other passages (committee rationale, evidence summaries) explain *why*; they are not the advice itself.
    """
    if _REC_NUMBER.search(text) or _TABLE_START.search(text):
        return True
    return bool(_CHOICE_SECTION.search(section)) and not text.lstrip().startswith("•")


def has_negation(text: str) -> bool:
    t = text.lower()
    return any(c in t for c in NEGATION_CUES)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def split_recommendations(reply: str) -> list[str]:
    """Pull advice-like sentences out of a free-text doctor reply (conservative heuristic)."""
    out = []
    for s in sentences(reply):
        low = s.lower()
        if s.endswith("?"):
            continue
        if any(v in low for v in ADVICE_VERBS) and len(s) > 15:
            out.append(s)
    return out[:10]
