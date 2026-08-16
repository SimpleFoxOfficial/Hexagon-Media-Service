"""Text repair and normalisation for names that end up on disk.

Two problems, both visible in filenames:

* Mojibake. A dub name like the Russian for "Original (+subtitles)" arrives as
  UTF-8 bytes that something decoded as Windows-1251, giving the familiar
  run of Cyrillic gibberish. It is reversible, so it is reversed.
* Mixed scripts. The interface is English, and a Cyrillic dub name in the
  middle of an otherwise Latin filename is awkward to type, search and sort.
  Known labels are translated and anything else is transliterated.
"""

from __future__ import annotations

import re
import unicodedata

# Which codepage the bytes were wrongly read as. CP1251 is the usual one for
# Cyrillic text; the others cover Latin-script sources.
_MOJIBAKE_CODECS = ("cp1251", "cp1252", "latin-1")

# UTF-8 Cyrillic begins with lead bytes D0/D1, which decode to these two
# letters under CP1251, so mis-decoded text is unnaturally full of them.
_LEAD_CHARS = "".join(map(chr, (0x420, 0x421)))  # Cyrillic ER and ES

# Marks that essentially only appear in mis-decoded text.
_JUNK_CHARS = set(
    map(
        chr,
        (
            0x402, 0x403, 0x404, 0x405, 0x406, 0x407, 0x490, 0x451,
            0x45B, 0x45F, 0x45E, 0x459, 0x45A, 0x453, 0x455, 0x458,
            0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2039, 0x203A,
        ),
    )
)

# Dub and release labels HDRezka uses, in English.
_KNOWN_LABELS = {
    "оригинал": "Original",
    "оригинал (+субтитры)": "Original + Subtitles",
    "оригинальная дорожка": "Original",
    "субтитры": "Subtitles",
    "украинский": "Ukrainian",
    "русский": "Russian",
    "английский": "English",
    "дублированный": "Dubbed",
    "дубляж": "Dubbed",
    "многоголосый": "Multivoice",
    "многоголосый закадровый": "Multivoice",
    "двухголосый": "Twovoice",
    "одноголосый": "Onevoice",
    "профессиональный": "Professional",
    "любительский": "Amateur",
}

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g",
}


def _mojibake_score(text: str) -> float:
    """How mis-decoded a string looks. Higher is worse."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    lead = sum(1 for ch in letters if ch in _LEAD_CHARS)
    junk = sum(1 for ch in text if ch in _JUNK_CHARS)
    # Real Russian uses these letters, but nowhere near every other character.
    return (lead / len(letters)) + (junk / max(1, len(text))) * 2


def repair_mojibake(text: str) -> str:
    """Undo a UTF-8 payload that was decoded as a single-byte codepage.

    Each candidate codepage is tried and the result kept only if it looks less
    mis-decoded than the input, so correct text is never damaged.
    """
    if not text:
        return text

    before = _mojibake_score(text)
    if before < 0.25:
        return text

    best, best_score = text, before
    for codec in _MOJIBAKE_CODECS:
        try:
            candidate = text.encode(codec, errors="strict").decode("utf-8", errors="strict")
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            continue
        score = _mojibake_score(candidate)
        if score < best_score:
            best, best_score = candidate, score

    return best


def transliterate(text: str) -> str:
    """Cyrillic to Latin, leaving anything already Latin alone."""
    out = []
    for char in text:
        lower = char.lower()
        if lower in _TRANSLIT:
            mapped = _TRANSLIT[lower]
            out.append(mapped.upper() if char.isupper() and mapped else mapped)
        else:
            out.append(char)
    return "".join(out)


def english_label(text: str) -> str:
    """A filename-safe English label for a dub or translation name."""
    if not text:
        return ""

    cleaned = repair_mojibake(str(text)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    key = cleaned.lower().strip(" .")
    if key in _KNOWN_LABELS:
        return _KNOWN_LABELS[key]

    # Some labels are "Studio (Original)" and similar; translate known parts.
    for known, english in _KNOWN_LABELS.items():
        if known in key:
            rest = re.sub(re.escape(known), "", key, flags=re.IGNORECASE)
            rest = transliterate(rest).strip(" ()+-,")
            rest = re.sub(r"\s+", " ", rest).strip()
            return f"{rest.title()} {english}".strip() if rest else english

    latin = transliterate(cleaned)
    latin = unicodedata.normalize("NFKD", latin)
    latin = "".join(ch for ch in latin if not unicodedata.combining(ch))
    latin = re.sub(r"[^\w\s().+-]", "", latin, flags=re.ASCII)
    return re.sub(r"\s+", " ", latin).strip(" .-_")


def clean_title(text: str) -> str:
    """Repair a show title without forcing it out of its own script."""
    return re.sub(r"\s+", " ", repair_mojibake(str(text or ""))).strip()
