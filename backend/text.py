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

    Handles the cases found in real rips (Addendum I):
    - one-layer mojibake (UTF-8 read as Latin-1/cp1252, cp1251 read
      as Latin-1);
    - MIXED strings, where cp1252-only characters (Ÿ, ') and raw C1
      control bytes sit in the same value - no single codec can
      re-encode those, so the original bytes are recovered leniently;
    - layered mojibake (mangled more than once): layers are peeled
      one at a time until the text stops changing;
    - the 'РџСЂ…' pattern (UTF-8 bytes once decoded as cp1251).

    A repair is only accepted when it clearly produces or approaches
    Russian text, so legitimate names like 'cafe' or 'Zoë' are left
    alone.
    """
    if not s:
        return s
    for _ in range(4):  # peel one layer per pass
        new = _fix_once(s)
        if new == s:
            break
        s = new
    return s


def _recover_bytes(s):
    """Best-effort recovery of the bytes a mojibake string came from.

    Each character is encoded as cp1252 when possible (covers the
    printable extras like Ÿ and '), otherwise as its raw byte value
    for characters up to U+00FF (covers the C1 control bytes cp1252
    leaves undefined). Returns None when a character fits neither -
    e.g. proper Cyrillic, which needs no repair.
    """
    out = bytearray()
    for ch in s:
        try:
            out += ch.encode("cp1252")
            continue
        except UnicodeEncodeError:
            pass
        o = ord(ch)
        if o <= 0xFF:
            out.append(o)
        else:
            return None
    return bytes(out)


def _fix_once(s):
    raw = _recover_bytes(s)

    # 1) The recovered bytes are UTF-8 (the common case, including
    #    mixed strings and outer layers of multi-mangled text). A
    #    successful strict UTF-8 decode is itself strong evidence:
    #    ordinary Latin-1 text almost never forms valid UTF-8. Peel
    #    the layer; the loop re-checks the result.
    if raw is not None:
        try:
            c = raw.decode("utf-8")
        except UnicodeDecodeError:
            c = None
        if c is not None and c != s and "\ufffd" not in c:
            return c

    # 2) The 'РџСЂ…' pattern: the string IS Cyrillic-looking, but its
    #    cp1251 bytes are themselves UTF-8. Proper Russian text
    #    essentially never survives this round trip, so a successful
    #    decode with a strong Cyrillic result is a true repair.
    try:
        c = s.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        c = None
    if c is not None and c != s and cyrillic_ratio(c) >= 0.4:
        return c

    # 3) cp1251 bytes read as Latin-1 (old ID3v2.3 rips). Only
    #    accepted when the result is clearly Russian and the input
    #    was not - this is the candidate that can false-positive on
    #    mangled noise, so it goes last and never starts from text
    #    that already looks Russian.
    if raw is not None and cyrillic_ratio(s) < 0.4:
        try:
            c = raw.decode("cp1251")
        except UnicodeDecodeError:
            c = None
        if c is not None and c != s and cyrillic_ratio(c) >= 0.5:
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
