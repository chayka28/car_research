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


def test_parse_listing_html_manyen_text_and_invalid_total_price() -> None:
    html = """
    <html>
      <body>
        <h1 class="title1">Toyota Prius S (レッド)</h1>
        <div class="specWrap__box">
          <p class="specWrap__box__title">年式</p>
          <p class="specWrap__box__num">2018</p>
        </div>
        <p class="basePrice__price"><span>8</span><span>0</span><span>.0</span>万円</p>
        <p class="totalPrice__price"><span>7</span><span>0</span><span>.0</span>万円</p>
        <table>
          <tr><th>色</th><td>レッド</td></tr>
        </table>
      </body>
    </html>
    """

    parsed = parse_listing_html(
        html=html,
        url="https://www.carsensor.net/usedcar/detail/AUTEST000001/index.html",
        external_id="AUTEST000001",
        final_url="https://www.carsensor.net/usedcar/detail/AUTEST000001/index.html",
        jpy_to_rub_rate=0.62,
    )

    assert isinstance(parsed, ListingData)
    assert parsed.price_jpy == 800_000
    assert parsed.price_rub == round(800_000 * 0.62)
    assert parsed.total_price_jpy is None
    assert parsed.total_price_rub is None
