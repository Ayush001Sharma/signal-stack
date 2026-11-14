"""Shared API dependencies: DB session, company lookup (tenant isolation), API-key auth, pagination."""
import secrets

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import Company


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def get_company(company_id: int, db: Session = Depends(get_db)) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    return company


class Pagination:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def owned(obj, company: Company, name: str = "Resource"):
    """404 unless obj exists and belongs to the company (prevents cross-company access)."""
    if obj is None or getattr(obj, "company_id", None) != company.id:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return obj
