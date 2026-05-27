from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_portfolio
from app.crud import portfolio as crud_portfolio
from app.db.session import get_session
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.schema_portfolio import PortfolioCreate, PortfolioRead

router = APIRouter()


@router.post("/", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    obj_in: PortfolioCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Portfolio:
    return await crud_portfolio.create_with_owner(
        db, obj_in=obj_in, owner_id=current_user.id
    )


@router.get("/", response_model=list[PortfolioRead])
async def read_portfolios(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    skip: int = 0,
    limit: int = 100,
) -> Sequence[Portfolio]:
    return await crud_portfolio.get_by_owner(
        db, owner_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def read_portfolio(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
) -> Portfolio:
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await crud_portfolio.remove(db, id=portfolio.id)