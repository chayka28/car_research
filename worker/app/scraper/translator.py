import re
import unicodedata

from pykakasi import kakasi


KAKASI = kakasi()

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
WHITESPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^A-Za-z0-9\s\-/+]")
ALNUM_RE = re.compile(r"[^a-z0-9]+")

MAKE_MAP = {
    "\u30c8\u30e8\u30bf": "Toyota",
    "\u65e5\u7523": "Nissan",
    "\u30db\u30f3\u30c0": "Honda",
    "\u30de\u30c4\u30c0": "Mazda",
    "\u30b9\u30d0\u30eb": "Subaru",
    "\u4e09\u83f1": "Mitsubishi",
    "\u30b9\u30ba\u30ad": "Suzuki",
    "\u30c0\u30a4\u30cf\u30c4": "Daihatsu",
    "\u30ec\u30af\u30b5\u30b9": "Lexus",
    "\u30a2\u30a6\u30c7\u30a3": "Audi",
    "BMW": "BMW",
    "\u30e1\u30eb\u30bb\u30c7\u30b9\u30fb\u30d9\u30f3\u30c4": "Mercedes-Benz",
    "\u30dd\u30eb\u30b7\u30a7": "Porsche",
    "\u30d5\u30a9\u30eb\u30af\u30b9\u30ef\u30fc\u30b2\u30f3": "Volkswagen",
    "\u30dc\u30eb\u30dc": "Volvo",
    "\u30b7\u30c8\u30ed\u30a8\u30f3": "Citroen",
    "\u30b7\u30c8\u30ed\u30a8\u30f3 ": "Citroen",
    "\u30d7\u30b8\u30e7\u30fc": "Peugeot",
    "\u30eb\u30ce\u30fc": "Renault",
    "\u30b8\u30e3\u30ac\u30fc": "Jaguar",
    "\u30e9\u30f3\u30c9\u30ed\u30fc\u30d0\u30fc": "Land Rover",
    "\u30d5\u30a3\u30a2\u30c3\u30c8": "Fiat",
    "\u30a2\u30d0\u30eb\u30c8": "Abarth",
    "\u30b8\u30fc\u30d7": "Jeep",
    "\u30d5\u30a9\u30fc\u30c9": "Ford",
    "\u30b7\u30dc\u30ec\u30fc": "Chevrolet",
    "\u30af\u30e9\u30a4\u30b9\u30e9\u30fc": "Chrysler",
    "\u30c6\u30b9\u30e9": "Tesla",
}

COLOR_MAP = {
    "\u30ec\u30c3\u30c9": "Red",
    "\u30d6\u30eb\u30fc": "Blue",
    "\u30db\u30ef\u30a4\u30c8": "White",
    "\u30d6\u30e9\u30c3\u30af": "Black",
    "\u30b7\u30eb\u30d0\u30fc": "Silver",
    "\u30b0\u30ec\u30fc": "Gray",
    "\u30ac\u30f3\u30e1\u30bf": "Gunmetal",
    "\u30ac\u30f3\u30e1\u30bf\u30ea\u30c3\u30af": "Gunmetal Metallic",
    "\u30d1\u30fc\u30eb": "Pearl",
    "\u30ef\u30a4\u30f3\u30ec\u30c3\u30c9": "Wine Red",
    "\u30cd\u30a4\u30d3\u30fc": "Navy",
    "\u30b0\u30ea\u30fc\u30f3": "Green",
    "\u30a4\u30a8\u30ed\u30fc": "Yellow",
    "\u30aa\u30ec\u30f3\u30b8": "Orange",
    "\u30d6\u30e9\u30a6\u30f3": "Brown",
    "\u30d9\u30fc\u30b8\u30e5": "Beige",
    "\u30b4\u30fc\u30eb\u30c9": "Gold",
    "\u30d4\u30f3\u30af": "Pink",
    "\u7d2b": "Purple",
    "\u30e9\u30a4\u30c8\u30d6\u30eb\u30fc": "Light Blue",
    "\u30c0\u30fc\u30af\u30d6\u30eb\u30fc": "Dark Blue",
    "\u30d1\u30fc\u30eb\u30db\u30ef\u30a4\u30c8": "Pearl White",
    "\u30db\u30ef\u30a4\u30c8\u30d1\u30fc\u30eb": "Pearl White",
    "\u30d6\u30eb\u30c3\u30af\u30ea\u30f3\u30b0\u30ec\u30fc\u30e1\u30bf\u30ea\u30c3\u30af": "Brooklyn Gray Metallic",
    "\u30db\u30ef\u30a4\u30c8\u30ce\u30fc\u30f4\u30a1\u30ac\u30e9\u30b9\u30d5\u30ec\u30fc\u30af": "White Nova Glass Flake",
    "\u30db\u30ef\u30a4\u30c8\u30ce\u30f4\u30a1\u30ac\u30e9\u30b9\u30d5\u30ec\u30fc\u30af": "White Nova Glass Flake",
    "\u30b0\u30ec\u30fc\u30e1\u30bf\u30ea\u30c3\u30af": "Gray Metallic",
    "\u30b7\u30eb\u30d0\u30fc\u30e1\u30bf\u30ea\u30c3\u30af": "Silver Metallic",
    "\u30ec\u30c3\u30c9\u30e1\u30bf\u30ea\u30c3\u30af": "Red Metallic",
    "\u30d6\u30eb\u30fc\u30e1\u30bf\u30ea\u30c3\u30af": "Blue Metallic",
    "\u30d6\u30e9\u30c3\u30af\u30e1\u30bf\u30ea\u30c3\u30af": "Black Metallic",
}

ROMANIZED_COLOR_MAP = {
    "howaitonoovuagarasufureeku": "White Nova Glass Flake",
    "howaitonovuagarasufureeku": "White Nova Glass Flake",
    "howaitonovagarasufureeku": "White Nova Glass Flake",
    "howaitonovagarasufureku": "White Nova Glass Flake",
    "burukkuringureemetarikku": "Brooklyn Gray Metallic",
    "buruukkuringureemetarikku": "Brooklyn Gray Metallic",
}

ROMANIZED_COLOR_TOKEN_MAP = [
    ("shainingu", "Shining"),
    ("metarikku", "Metallic"),
    ("howaito", "White"),
    ("burakku", "Black"),
    ("buruu", "Blue"),
    ("guree", "Gray"),
    ("guriin", "Green"),
    ("gurin", "Green"),
    ("reddo", "Red"),
    ("orenji", "Orange"),
    ("beju", "Beige"),
    ("shirubaa", "Silver"),
    ("shiruba", "Silver"),
    ("paaru", "Pearl"),
    ("arupin", "Alpine"),
]
ENGLISH_COLOR_KEYWORDS = {
    "white",
    "black",
    "blue",
    "gray",
    "green",
    "red",
    "orange",
    "beige",
    "silver",
    "pearl",
    "metallic",
}

MODEL_REPLACEMENTS = {
    "shiriizu": "Series",
    "shirizu": "Series",
    "supootsu": "Sports",
}


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value).replace("\xa0", " ").strip()
    text = WHITESPACE_RE.sub(" ", text)
    return text or None


def _romanize(value: str) -> str:
    parts = KAKASI.convert(value)
    return "".join(item.get("hepburn") or item.get("orig", "") for item in parts)


def _cleanup_ascii(value: str) -> str:
    text = NON_WORD_RE.sub(" ", value)
    text = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def _title_or_upper_words(value: str) -> str:
    words: list[str] = []
    for token in value.split(" "):
        if not token:
            continue
        if re.fullmatch(r"[A-Z0-9\-/+]+", token):
            words.append(token)
            continue
        if token.upper() in {"BMW", "GT", "AMG", "SUV", "WRX"}:
            words.append(token.upper())
            continue
        words.append(token.capitalize())
    return " ".join(words)


def _compact_ascii_key(value: str) -> str:
    return ALNUM_RE.sub("", value.lower())


def _normalize_romanized_color_phrase(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None

    text = normalized.lower()
    replaced = text
    for token, replacement in ROMANIZED_COLOR_TOKEN_MAP:
        replaced = re.sub(token, f" {replacement} ", replaced, flags=re.IGNORECASE)

    replaced = WHITESPACE_RE.sub(" ", replaced).strip()
    if not replaced:
        return None

    words = [word.lower() for word in replaced.split(" ")]
    if not any(keyword in words for keyword in ENGLISH_COLOR_KEYWORDS):
        return None
    return _title_or_upper_words(replaced)


def _translate_generic(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None

    if CJK_RE.search(normalized):
        normalized = _romanize(normalized)

    for src, dst in MODEL_REPLACEMENTS.items():
        normalized = re.sub(src, dst, normalized, flags=re.IGNORECASE)

    normalized = _cleanup_ascii(normalized)
    if not normalized:
        return None
    return _title_or_upper_words(normalized)


def translate_make(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    mapped = MAKE_MAP.get(normalized)
    if mapped:
        return mapped
    translated = _translate_generic(normalized)
    return translated or normalized


def translate_model(value: str | None) -> str | None:
    return _translate_generic(value)


def translate_color(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    mapped = COLOR_MAP.get(normalized)
    if mapped:
        return mapped
    romanized_mapped = ROMANIZED_COLOR_MAP.get(_compact_ascii_key(normalized))
    if romanized_mapped:
        return romanized_mapped
    romanized_phrase = _normalize_romanized_color_phrase(normalized)
    if romanized_phrase:
        return romanized_phrase

    if "\u30b0\u30ec\u30fc" in normalized and "\u30e1\u30bf\u30ea\u30c3\u30af" in normalized:
        return "Gray Metallic"
    if "\u30b7\u30eb\u30d0\u30fc" in normalized and "\u30e1\u30bf\u30ea\u30c3\u30af" in normalized:
        return "Silver Metallic"
    if "\u30d6\u30eb\u30fc" in normalized and "\u30e1\u30bf\u30ea\u30c3\u30af" in normalized:
        return "Blue Metallic"
    if "\u30ec\u30c3\u30c9" in normalized and "\u30e1\u30bf\u30ea\u30c3\u30af" in normalized:
        return "Red Metallic"
    if "\u30d6\u30e9\u30c3\u30af" in normalized and "\u30e1\u30bf\u30ea\u30c3\u30af" in normalized:
        return "Black Metallic"
    if "\u30e9\u30a4\u30c8" in normalized and "\u30d6\u30eb\u30fc" in normalized:
        return "Light Blue"
    if "\u30d1\u30fc\u30eb" in normalized and "\u30db\u30ef\u30a4\u30c8" in normalized:
        return "Pearl White"

    translated = _translate_generic(normalized)
    if not translated:
        return normalized

    romanized_mapped = ROMANIZED_COLOR_MAP.get(_compact_ascii_key(translated))
    if romanized_mapped:
        return romanized_mapped
    romanized_phrase = _normalize_romanized_color_phrase(translated)
    if romanized_phrase:
        return romanized_phrase
    return translated
