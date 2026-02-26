import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.scraper.translator import translate_color, translate_make, translate_model


logger = logging.getLogger(__name__)

UNAVAILABLE_MARKERS = (
    "\u63b2\u8f09\u7d42\u4e86",
    "\u3053\u306e\u8eca\u4e21\u306f",
    "\u3053\u306e\u8eca\u4e21\u306e\u63b2\u8f09\u306f\u7d42\u4e86\u3057\u307e\u3057\u305f",
    "\u8ca9\u58f2\u7d42\u4e86",
    "\u6210\u7d04\u6e08\u307f",
    "Listing appears unavailable",
)

YEAR_LABEL = "\u5e74\u5f0f"
COLOR_LABEL = "\u8272"
MILEAGE_LABEL = "\u8d70\u884c\u8ddd\u96e2"
REGION_LABEL = "\u5730\u57df"

SHOP_LABEL = "\u8ca9\u58f2\u5e97"
ADDRESS_LABEL = "\u4f4f\u6240"
PHONE_LABEL = "\u96fb\u8a71\u756a\u53f7"
TRANSMISSION_LABEL = "\u30df\u30c3\u30b7\u30e7\u30f3"
DRIVE_LABEL = "\u99c6\u52d5\u65b9\u5f0f"
ENGINE_CC_LABEL = "\u6392\u6c17\u91cf"
FUEL_LABEL = "\u71c3\u6599"
STEERING_LABEL = "\u30cf\u30f3\u30c9\u30eb"
BODY_TYPE_LABEL = "\u30dc\u30c7\u30a3\u30bf\u30a4\u30d7"

DIGITS_RE = re.compile(r"\d+")
YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")
PRICE_MANYEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\u4e07")
MILEAGE_MANYEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\u4e07\s*km", re.IGNORECASE)
PAREN_COLOR_RE = re.compile(r"[\uFF08(]\s*([^()\uFF08\uFF09]+)\s*[\uFF09)]")
SPACE_RE = re.compile(r"\s+")
MANYEN_MULTIPLIER = 10_000
PRICE_NOT_SPECIFIED_JPY_THRESHOLD = 90_000_000
INVALID_PRICE_JPY_VALUES = {99_999_999, 999_999_999}
PRICE_NOT_SPECIFIED_MARKERS = (
    "\u5fdc\u8ac7",
    "\u4fa1\u683c\u5fdc\u8ac7",
    "\u8981\u76f8\u8ac7",
    "\u8981\u554f\u5408\u305b",
    "ASK",
    "TBD",
)


@dataclass
class ListingData:
    external_id: str
    url: str
    make: str
    model: str
    year: int
    price_jpy: int | None
    price_rub: int | None
    color: str
    grade: str | None
    mileage_km: int | None
    total_price_jpy: int | None
    total_price_rub: int | None
    prefecture: str | None
    shop_name: str | None
    shop_address: str | None
    shop_phone: str | None
    transmission: str | None
    drive_type: str | None
    engine_cc: int | None
    fuel: str | None
    steering: str | None
    body_type: str | None
    scraped_at: datetime


@dataclass
class ParseFailure:
    error_type: str
    message: str
    status_code: int | None = None
    debug_snippet: str | None = None
    unavailable: bool = False


@dataclass
class QuickMakeData:
    make: str | None
    model: str | None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()
    return text or None


def _node_text(node) -> str | None:
    if node is None:
        return None
    return _clean_text(node.get_text(" ", strip=True))


def _to_int_digits(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(DIGITS_RE.findall(value))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _price_node_text(node) -> str | None:
    if node is None:
        return None
    text = "".join(node.stripped_strings).replace(",", "").replace("пјЊ", "").replace(" ", "")
    return text or None


def _parse_manyen_text_to_jpy(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace("пјЋ", ".").replace(",", "").replace("пјЊ", "").replace(" ", "")
    manyen_match = PRICE_MANYEN_RE.search(normalized)
    if not manyen_match:
        return None
    try:
        parsed = int(round(float(manyen_match.group(1)) * MANYEN_MULTIPLIER))
    except ValueError:
        return None
    return _sanitize_price_jpy(parsed)


def _sanitize_price_jpy(value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0:
        return None
    if value in INVALID_PRICE_JPY_VALUES:
        return None
    if value >= PRICE_NOT_SPECIFIED_JPY_THRESHOLD:
        return None
    return value


def _parse_numeric_content_to_jpy(content_value: str | None) -> int | None:
    parsed = _to_int_digits(content_value.replace(",", "").replace("пјЊ", "")) if content_value else None
    if parsed is None:
        return None
    if parsed < MANYEN_MULTIPLIER:
        parsed *= MANYEN_MULTIPLIER
    return _sanitize_price_jpy(parsed)


def _parse_mileage_km(value: str | None) -> int | None:
    if not value:
        return None
    text = value.replace(",", "")
    manyen_match = MILEAGE_MANYEN_RE.search(text)
    if manyen_match:
        try:
            return int(round(float(manyen_match.group(1)) * 10000))
        except ValueError:
            return None
    return _to_int_digits(text)


def _extract_label_map(soup: BeautifulSoup) -> dict[str, str]:
    label_map: dict[str, str] = {}

    for box in soup.select("div.specWrap__box"):
        key = _node_text(box.select_one("p.specWrap__box__title"))
        value = _node_text(box.select_one("p.specWrap__box__num"))
        if key and value and key not in label_map:
            label_map[key] = value

    for row in soup.select("tr"):
        key = _node_text(row.find("th"))
        value = _node_text(row.find("td"))
        if key and value and key not in label_map:
            label_map[key] = value

    for dl in soup.select("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = _node_text(dt)
            value = _node_text(dd)
            if key and value and key not in label_map:
                label_map[key] = value

    return label_map


def _extract_make_model_grade_color_from_title(title_text: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    if not title_text:
        return None, None, None, None
    text = _clean_text(title_text) or ""
    color_match = PAREN_COLOR_RE.search(text)
    color = _clean_text(color_match.group(1)) if color_match else None
    text_no_color = PAREN_COLOR_RE.sub("", text).strip()

    parts = [part for part in text_no_color.split(" ") if part]
    make = parts[0] if len(parts) >= 1 else None
    model = parts[1] if len(parts) >= 2 else None
    grade = " ".join(parts[2:]) if len(parts) >= 3 else None
    return make, model, grade, color


def _extract_year_from_spec_boxes(soup: BeautifulSoup, url: str) -> tuple[int | None, list[str]]:
    found_titles: list[str] = []
    for box in soup.select("div.specWrap__box"):
        title = _node_text(box.select_one("p.specWrap__box__title")) or ""
        found_titles.append(title)
        if YEAR_LABEL not in title:
            continue
        raw_year = _node_text(box.select_one("p.specWrap__box__num"))
        if not raw_year:
            logger.warning("Year block found but value missing for %s", url)
            return None, found_titles
        year_match = YEAR_RE.search(raw_year)
        if not year_match:
            logger.warning("Failed to parse year for %s from raw value %r", url, raw_year)
            return None, found_titles
        try:
            return int(year_match.group(1)), found_titles
        except ValueError:
            return None, found_titles
    logger.warning("Year not found for %s. Found spec titles: %s", url, found_titles)
    return None, found_titles


def _parse_base_price_jpy(soup: BeautifulSoup, url: str) -> tuple[int | None, str | None]:
    price_tag = soup.select_one("p.basePrice__price")
    if price_tag is None:
        message = "price_tag_missing"
        logger.warning("Price tag missing for %s", url)
        return None, message

    text_value = _price_node_text(price_tag)
    if text_value:
        upper_text = text_value.upper()
        if any(marker in text_value or marker in upper_text for marker in PRICE_NOT_SPECIFIED_MARKERS):
            logger.info("Price is marked as not specified for %s", url)
            return None, "price_not_specified"

        manyen_price = _parse_manyen_text_to_jpy(text_value)
        if manyen_price is not None:
            return manyen_price, None

    content_value = price_tag.get("content")
    if content_value:
        parsed = _parse_numeric_content_to_jpy(str(content_value))
        if parsed is not None:
            return parsed, None
        logger.warning("Failed to parse base price content for %s. content=%r", url, content_value)
    else:
        logger.warning("Price content attribute missing for %s", url)

    if text_value:
        parsed_digits = _to_int_digits(text_value)
        if parsed_digits is not None:
            if parsed_digits < MANYEN_MULTIPLIER:
                parsed_digits *= MANYEN_MULTIPLIER
            parsed_digits = _sanitize_price_jpy(parsed_digits)
            if parsed_digits is not None:
                return parsed_digits, None

    return None, "price_content_missing_or_invalid"


def _parse_total_price_jpy(soup: BeautifulSoup) -> int | None:
    node = soup.select_one("p.totalPrice__price")
    if node is None:
        return None

    text_value = _price_node_text(node)
    if text_value:
        upper_text = text_value.upper()
        if any(marker in text_value or marker in upper_text for marker in PRICE_NOT_SPECIFIED_MARKERS):
            return None

        manyen_price = _parse_manyen_text_to_jpy(text_value)
        if manyen_price is not None:
            return manyen_price

    content_value = node.get("content")
    if content_value:
        parsed = _parse_numeric_content_to_jpy(str(content_value))
        if parsed is not None:
            return parsed

    if not text_value:
        return None
    parsed_digits = _to_int_digits(text_value)
    if parsed_digits is None:
        return None
    if parsed_digits < MANYEN_MULTIPLIER:
        parsed_digits *= MANYEN_MULTIPLIER
    return _sanitize_price_jpy(parsed_digits)


def check_listing_unavailable(html: str, final_url: str) -> bool:
    if "/usedcar/search.php" in final_url:
        return True
    text = _clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)) or ""
    return any(marker in text for marker in UNAVAILABLE_MARKERS)


def quick_extract_make_model(html: str) -> QuickMakeData:
    soup = BeautifulSoup(html, "html.parser")
    title_text = _node_text(soup.select_one("h1.title1")) or _node_text(soup.find("h1"))
    make_raw, model_raw, _grade, _color = _extract_make_model_grade_color_from_title(title_text)
    return QuickMakeData(make=translate_make(make_raw), model=translate_model(model_raw))


def parse_listing_html(
    *,
    html: str,
    url: str,
    external_id: str,
    final_url: str,
    jpy_to_rub_rate: float,
) -> ListingData | ParseFailure:
    if check_listing_unavailable(html, final_url):
        return ParseFailure(
            error_type="listing_unavailable",
            message="Listing appears unavailable",
            debug_snippet=html[:800],
            unavailable=True,
        )

    soup = BeautifulSoup(html, "html.parser")
    label_map = _extract_label_map(soup)

    title_text = _node_text(soup.select_one("h1.title1")) or _node_text(soup.find("h1"))
    make_raw, model_raw, grade_raw, color_from_title = _extract_make_model_grade_color_from_title(title_text)

    make = translate_make(make_raw)
    model = translate_model(model_raw)
    color = translate_color(label_map.get(COLOR_LABEL) or color_from_title)
    grade = translate_model(grade_raw)

    year, found_year_titles = _extract_year_from_spec_boxes(soup, url)
    if year is None:
        return ParseFailure(
            error_type="missing_year",
            message=f"Missing year; found spec titles: {found_year_titles}",
            debug_snippet=html[:800],
        )

    price_jpy, price_error = _parse_base_price_jpy(soup, url)
    total_price_jpy = _parse_total_price_jpy(soup)
    if price_jpy is not None and total_price_jpy is not None and total_price_jpy < price_jpy:
        logger.warning(
            "Total price looks invalid for %s (total=%s < base=%s). Dropping total price.",
            url,
            total_price_jpy,
            price_jpy,
        )
        total_price_jpy = None

    if price_jpy is None and total_price_jpy is None:
        logger.info("Price not specified for %s (%s)", url, price_error or "unknown")

    mileage_km = _parse_mileage_km(label_map.get(MILEAGE_LABEL))

    prefecture = label_map.get(REGION_LABEL)
    transmission = label_map.get(TRANSMISSION_LABEL) or label_map.get("AT/CVT")
    drive_type = label_map.get(DRIVE_LABEL) or label_map.get("\u99c6\u52d5")
    engine_cc = _to_int_digits(label_map.get(ENGINE_CC_LABEL))
    fuel = label_map.get(FUEL_LABEL)
    steering = label_map.get(STEERING_LABEL)
    body_type = label_map.get(BODY_TYPE_LABEL)
    shop_name = label_map.get(SHOP_LABEL) or _node_text(soup.select_one(".shopName"))
    shop_address = label_map.get(ADDRESS_LABEL) or _node_text(soup.select_one(".shopAddress"))
    shop_phone = label_map.get(PHONE_LABEL) or _node_text(soup.select_one(".shopPhone"))

    translated_make = make or "Unknown"
    translated_model = model or "Unknown"
    translated_color = color or "Unknown"

    price_rub = int(round(price_jpy * jpy_to_rub_rate)) if price_jpy is not None else None
    total_price_rub = int(round(total_price_jpy * jpy_to_rub_rate)) if total_price_jpy is not None else None

    return ListingData(
        external_id=external_id,
        url=url,
        make=translated_make,
        model=translated_model,
        year=year,
        price_jpy=price_jpy,
        price_rub=price_rub,
        color=translated_color,
        grade=grade,
        mileage_km=mileage_km,
        total_price_jpy=total_price_jpy,
        total_price_rub=total_price_rub,
        prefecture=prefecture,
        shop_name=shop_name,
        shop_address=shop_address,
        shop_phone=shop_phone,
        transmission=transmission,
        drive_type=drive_type,
        engine_cc=engine_cc,
        fuel=fuel,
        steering=steering,
        body_type=body_type,
        scraped_at=datetime.now(timezone.utc),
    )

