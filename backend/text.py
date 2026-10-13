"""Text repair utilities: mojibake fixing, safe Windows filenames,
transliterated-Russian detection, and language guessing.

Transliteration detection is heuristic and is used ONLY to flag items
for human review - nothing is ever auto-renamed based on it.
"""

import re

CYRILLIC = re.compile(r"[\u0400-\u04FF]")
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)  # any unicode letter
WINDOWS_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                    | {f"COM{i}" for i in range(1, 10)}
                    | {f"LPT{i}" for i in range(1, 10)})


def cyrillic_ratio(s):
    letters = LETTER.findall(s or "")
    if not letters:
        return 0.0
    return sum(1 for ch in letters if CYRILLIC.match(ch)) / len(letters)


def fix_mojibake(s):
    """Repair Cyrillic text mangled by wrong-encoding reads
    (e.g. 'ÐŸÑ€Ð¸Ð²ÐµÑ‚' -> 'Привет').

    A repair is only accepted when it clearly produces Russian text, so
    legitimate names like 'cafe' or 'Zoë' are left alone.
    """
    if not s:
        return s
    for _ in range(3):  # handle double-mangled text
        new = _fix_once(s)
        if new == s:
            break
        s = new
    return s


def _fix_once(s):
    candidates = []
    for enc in ("latin-1", "cp1252"):
        try:
            candidates.append(s.encode(enc).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    try:
        candidates.append(s.encode("latin-1").decode("cp1251"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    for c in candidates:
        if c != s and cyrillic_ratio(c) >= 0.4:
            return c
    return s


TRANSLIT_MARKERS = ["shch", "zh", "kh", "ts", "ch", "sh", "yu", "ya",
                    "ye", "yo", "iy", "yy"]
TRANSLIT_ENDINGS = ("ov", "ev", "in", "yn", "sky", "skiy", "aya",
                    "yaya", "ova", "eva", "ina", "ogo", "ovich")
RU_KEYWORDS = {
    # famous works (transliterated)
    "voina", "mir", "prestuplenie", "nakazanie", "idiot", "bratya",
    "karamazov", "karamazovy", "anna", "karenina", "master", "margarita",
    "mertvye", "dushi", "revizor", "shinel", "nos", "viy",
    "oblomov", "geroy", "nashego", "vremeni", "evgeniy", "onegin",
    "pikovaya", "dama", "kapitanskaya", "dochka", "tikhi", "don",
    "doktor", "zhivago", "arkhipelag", "gulag", "piknik", "stalker",
    "metro", "dozor", "azazel", "gore", "uma",
    # famous authors (transliterated)
    "tolstoy", "tolstoi", "dostoevsky", "dostoevski", "dostoevskiy",
    "pushkin", "gogol", "chekhov", "chehov", "turgenev", "bulgakov",
    "solzhenitsyn", "solzhenitsin", "pasternak", "nabokov", "akhmatova",
    "akhmatowa", "tsvetaeva", "mayakovsky", "mayakovski", "yesenin",
    "esenin", "lermontov", "bunin", "sholokhov", "sholohov", "grossman",
    "strugatsky", "strugatskie", "pelevin", "akunin", "lukyanenko",
    "glukhovsky", "glukhovski", "rubina", "ulitskaya",
}


def looks_transliterated(s):
    """Heuristic: does this Latin-script text look like transliterated
    Russian? Used only to build a review list - never auto-renamed."""
    s = s or ""
    if CYRILLIC.search(s):
        return False
    low = s.lower()
    score = sum(1 for m in TRANSLIT_MARKERS if m in low)
    words = re.findall(r"[a-z']+", low)
    if any(w.endswith(TRANSLIT_ENDINGS) for w in words if len(w) > 3):
        score += 2
    if any(w in RU_KEYWORDS for w in words):
        score += 3
    return score >= 2


def guess_language(author, book, title):
    blob = " ".join([author or "", book or "", title or ""])
    if CYRILLIC.search(fix_mojibake(blob)):
        return "Russian"
    if looks_transliterated(blob):
        return "Russian (transliterated?)"
    return "English / other"


def clean_name(s, maxlen=80):
    """Make a string safe as a Windows file/folder name."""
    s = fix_mojibake(s or "")
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s:
        s = "Unknown"
    if s.upper() in WINDOWS_RESERVED:
        s = "_" + s
    return s[:maxlen]
