"""Business workspace CRUD endpoints.

The MVP is single-tenant and unauthenticated; the ``/api/businesses``
collection is the workspace switcher. ``X-Business-Id`` is therefore
informational only and not enforced — the path always carries the
identifier.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.schemas.business import BusinessCreate, BusinessRead, BusinessUpdate

router = APIRouter(prefix="/businesses", tags=["businesses"])


def _to_read(b: Business) -> BusinessRead:
    return BusinessRead(
        id=b.id,
        name=b.name,
        industry=b.industry,
        currency=b.currency,
        fiscal_year_start_month=b.fiscal_year_start_month,
        locale=b.locale,
        min_cash_reserve=str(b.min_cash_reserve),
        target_operating_margin=str(b.target_operating_margin),
        max_unsold_inventory_exposure_pct=str(b.max_unsold_inventory_exposure_pct),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


@router.get("", response_model=list[BusinessRead])
def list_businesses(db: Session = Depends(get_db)) -> list[BusinessRead]:
    """List all business workspaces (ordered by created_at desc)."""
    rows = db.query(Business).order_by(Business.created_at.desc()).all()
    return [_to_read(b) for b in rows]


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)) -> BusinessRead:
    """Create a new workspace."""
    try:
        b = Business(
            name=payload.name,
            industry=payload.industry.value,
            currency=payload.currency.value,
            fiscal_year_start_month=payload.fiscal_year_start_month,
            locale=payload.locale,
            min_cash_reserve=Decimal(payload.min_cash_reserve),
            target_operating_margin=Decimal(payload.target_operating_margin),
            max_unsold_inventory_exposure_pct=Decimal(payload.max_unsold_inventory_exposure_pct),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid business payload: {exc}") from exc
    db.add(b)
    db.commit()
    db.refresh(b)
    return _to_read(b)


@router.get("/{business_id}", response_model=BusinessRead)
def get_business(business_id: str, db: Session = Depends(get_db)) -> BusinessRead:
    b = db.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    return _to_read(b)


@router.patch("/{business_id}", response_model=BusinessRead)
def update_business(
    business_id: str, payload: BusinessUpdate, db: Session = Depends(get_db)
) -> BusinessRead:
    b = db.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    data = payload.model_dump(exclude_unset=True)
    # Normalise enums to their string values for the DB column.
    if "industry" in data and data["industry"] is not None:
        data["industry"] = data["industry"].value
    if "currency" in data and data["currency"] is not None:
        data["currency"] = data["currency"].value
    decimal_fields = {
        "min_cash_reserve",
        "target_operating_margin",
        "max_unsold_inventory_exposure_pct",
    }
    for k in list(data.keys()):
        if k in decimal_fields and data[k] is not None:
            try:
                data[k] = Decimal(data[k])
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"Invalid {k}: {data[k]!r}") from exc
    for k, v in data.items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return _to_read(b)


@router.delete("/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business(business_id: str, db: Session = Depends(get_db)) -> None:
    b = db.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    db.delete(b)
    db.commit()
    return None


__all__ = ["router"]
