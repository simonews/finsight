import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_portfolio
from app.crud import portfolio as crud_portfolio
from app.crud import position as crud_position
from app.db.session import get_session
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.user import User
from app.schemas.schema_position import PositionCreate, PositionRead

router = APIRouter()


@router.post("/", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
async def create_position(
    obj_in: PositionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Position:
    portfolio = await crud_portfolio.get(db, obj_in.portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found"
        )
    if portfolio.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return await crud_position.create(db, obj_in=obj_in)


@router.get("/portfolio/{portfolio_id}", response_model=list[PositionRead])
async def read_positions_by_portfolio(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Sequence[Position]:
    return await crud_position.get_by_portfolio(db, portfolio_id=portfolio.id)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    position = await crud_position.get(db, position_id)
    if position is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position not found"
        )
    owner_portfolio = await crud_portfolio.get(db, position.portfolio_id)
    if owner_portfolio is None or owner_portfolio.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    await crud_position.remove(db, id=position_id)