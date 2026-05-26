import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import position as crud_position
from app.db.session import get_session
from app.models.position import Position
from app.schemas.schema_position import PositionCreate, PositionRead

router = APIRouter()


@router.post("/", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
async def create_position(
    obj_in: PositionCreate,
    db: AsyncSession = Depends(get_session),
) -> Position:
    return await crud_position.create(db, obj_in=obj_in)


@router.get("/portfolio/{portfolio_id}", response_model=list[PositionRead])
async def read_positions_by_portfolio(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> Sequence[Position]:
    return await crud_position.get_by_portfolio(db, portfolio_id=portfolio_id)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> None:
    obj = await crud_position.remove(db, id=position_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position not found"
        )