from math import ceil
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_username
from app.db.session import get_db
from app.models.car import Car
from app.models.listing import Listing
from app.schemas.car import CarOut
from app.schemas.listing import ListingOut, ListingPageOut

router = APIRouter(prefix="/api", tags=["cars"])
SENTINEL_PRICE_MAX = 2_147_483_647
PLACEHOLDER_PRICE_VALUES = {999_999_999, 99_999_999, 69_999_999, 619_999_999}
MAX_REASONABLE_PRICE = 80_000_000
PRICE_NOT_SPECIFIED_TEXT = "price not specified"


def _normalize_price(value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0 or value >= SENTINEL_PRICE_MAX:
        return None
    if value in PLACEHOLDER_PRICE_VALUES:
        return None
    if value > MAX_REASONABLE_PRICE:
        return None
    return value


def _listing_price(item: Listing) -> int | None:
    return (
        _normalize_price(item.total_price_rub)
        or _normalize_price(item.price_rub)
        or _normalize_price(item.total_price_jpy)
        or _normalize_price(item.price_jpy)
    )


def _to_listing_out(item: Listing) -> ListingOut:
    listing_price = _listing_price(item)
    return ListingOut(
        id=item.id,
        external_id=item.external_id,
        source=item.source,
        brand=item.maker,
        model=item.model,
        year=item.year,
        price=listing_price,
        price_text=PRICE_NOT_SPECIFIED_TEXT if listing_price is None else None,
        price_jpy=item.price_jpy,
        price_rub=item.price_rub,
        color=item.color,
        link=item.url,
        is_active=item.is_active,
        last_seen_at=item.last_seen_at,
    )


@router.get("/cars", response_model=List[CarOut])
def list_cars(_: str = Depends(get_current_username), db: Session = Depends(get_db)) -> List[CarOut]:
    price_expr = func.coalesce(
        func.nullif(func.nullif(Listing.total_price_rub, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.price_rub, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.total_price_jpy, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.price_jpy, SENTINEL_PRICE_MAX), 0),
    )

    listings = db.scalars(
        select(Listing)
        .where(Listing.source == "carsensor")
        .where(Listing.is_active.is_(True))
        .where(Listing.deleted_at.is_(None))
        .where(Listing.maker != "Unknown")
        .where(Listing.model != "Unknown")
        .where(Listing.year.is_not(None))
        .where(price_expr.is_not(None))
        .where(price_expr > 0)
        .order_by(Listing.last_seen_at.desc(), Listing.id.desc())
    ).all()
    if listings:
        return [
            CarOut(
                brand=item.maker,
                model=item.model,
                year=item.year or 0,
                price=_listing_price(item) or 0,
                color=item.color or "Unknown",
                link=item.url,
            )
            for item in listings
        ]

    cars = db.scalars(select(Car).order_by(Car.id.desc())).all()
    return [
        CarOut(
            brand=car.brand,
            model=car.model,
            year=car.year,
            price=car.price,
            color=car.color,
            link=car.link,
        )
        for car in cars
    ]


@router.get("/listings", response_model=ListingPageOut)
def list_listings(
    _: str = Depends(get_current_username),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=200),
    query: str | None = Query(None, min_length=1, max_length=120),
    sort_by: Literal["updated", "brand", "model", "year", "price", "status"] = "updated",
    sort_order: Literal["asc", "desc"] = "desc",
    is_active: bool | None = Query(None),
    include_unknown: bool = Query(False),
) -> ListingPageOut:
    price_expr = func.coalesce(
        func.nullif(func.nullif(Listing.total_price_rub, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.price_rub, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.total_price_jpy, SENTINEL_PRICE_MAX), 0),
        func.nullif(func.nullif(Listing.price_jpy, SENTINEL_PRICE_MAX), 0),
    )

    stmt = select(Listing).where(Listing.source == "carsensor")

    if is_active is not None:
        stmt = stmt.where(Listing.is_active.is_(is_active))

    if not include_unknown:
        stmt = stmt.where(Listing.maker != "Unknown").where(Listing.model != "Unknown")

    if query:
        term = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Listing.maker).like(term),
                func.lower(Listing.model).like(term),
                func.lower(func.coalesce(Listing.color, "")).like(term),
                func.lower(Listing.external_id).like(term),
            )
        )

    sort_column = {
        "updated": Listing.last_seen_at,
        "brand": Listing.maker,
        "model": Listing.model,
        "year": Listing.year,
        "price": price_expr,
        "status": Listing.is_active,
    }[sort_by]

    if sort_order == "asc":
        order_clause = asc(sort_column).nullslast()
    else:
        order_clause = desc(sort_column).nullslast()
    stmt = stmt.order_by(order_clause, desc(Listing.id))

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    pages = max(1, ceil(total / per_page)) if total else 1

    items = db.scalars(stmt.offset((page - 1) * per_page).limit(per_page)).all()
    return ListingPageOut(
        items=[_to_listing_out(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    listing_id: int,
    _: str = Depends(get_current_username),
    db: Session = Depends(get_db),
) -> Response:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    db.delete(listing)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
