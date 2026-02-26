from pathlib import Path

from app.scraper.parser import ListingData, parse_listing_html


def test_parse_listing_html_prices_year_color_and_mileage() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "carsensor_detail.html"
    html = fixture_path.read_text(encoding="utf-8")

    parsed = parse_listing_html(
        html=html,
        url="https://www.carsensor.net/usedcar/detail/AU5867522762/index.html",
        external_id="AU5867522762",
        final_url="https://www.carsensor.net/usedcar/detail/AU5867522762/index.html",
        jpy_to_rub_rate=0.62,
    )

    assert isinstance(parsed, ListingData)
    assert parsed.total_price_jpy == 8_800_000
    assert parsed.price_jpy == 8_670_000
    assert parsed.total_price_rub == round(8_800_000 * 0.62)
    assert parsed.price_rub == round(8_670_000 * 0.62)
    assert parsed.year == 2011
    assert parsed.color == "Red"
    assert parsed.mileage_km == 34_000
    assert parsed.make == "BMW"
    assert parsed.model == "3 Series"
