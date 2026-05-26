from app.crud.base import CRUDBase
from app.models.portfolio import Portfolio
from app.schemas.schema_portfolio import PortfolioCreate, PortfolioUpdate


class CRUDPortfolio(CRUDBase[Portfolio, PortfolioCreate, PortfolioUpdate]):
    pass


portfolio = CRUDPortfolio(Portfolio)