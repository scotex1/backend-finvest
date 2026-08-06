"""
routes/investment_routes.py — /api/v1/engines/*
All 7 financial engine endpoints with plan-based access control

FIXED vs v1:
 [1] Portfolio + Retirement now save results to Firestore (per-user history)
 [2] Stock analysis now saves results to Firestore
 [3] New /investment-advice endpoint wires up InvestmentEngine (previously
     built but never connected to any route) + saves result
"""

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Optional
from middleware.access_middleware import require_plan

from engines.risk_profile          import RiskProfileEngine
from engines.goal_planner          import GoalPlannerEngine
from engines.retirement_calculator import RetirementEngine
from engines.portfolio_optimizer   import PortfolioEngine
from engines.stock_analysis        import StockAnalysisEngine
from engines.news_analysis         import NewsEngine
from engines.global_event_engine   import GlobalEventEngine
from engines.investment_engine     import InvestmentEngine
from firebase.firebase_service     import EngineDataService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ════════════════════════════════════════════════════════════
# FREE ENGINES
# ════════════════════════════════════════════════════════════

class RiskProfileRequest(BaseModel):
    score:   int
    profile: str
    answers: list

@router.post("/risk-profile", dependencies=[Depends(require_plan("risk-profile"))])
async def risk_profile(body: RiskProfileRequest, request: Request):
    uid    = request.state.uid
    result = RiskProfileEngine.save_and_analyze(uid, body.score, body.profile, body.answers)
    return result


@router.get("/news", dependencies=[Depends(require_plan("news"))])
async def get_news(request: Request, category: str = "all"):
    result = await NewsEngine.get_curated_news(category=category)
    return result


# ════════════════════════════════════════════════════════════
# BASIC ENGINES
# ════════════════════════════════════════════════════════════

class GoalRequest(BaseModel):
    goal_type:    str
    goal_name:    str
    target_amount: float
    target_date:  str
    current_saved: float = 0
    annual_return: float = 12.0

@router.post("/goal-planner", dependencies=[Depends(require_plan("goal-planner"))])
async def goal_planner(body: GoalRequest, request: Request):
    uid    = request.state.uid
    result = GoalPlannerEngine.calculate(uid, body.model_dump())
    return result


class RetirementRequest(BaseModel):
    current_age:      int
    retire_age:       int
    life_expectancy:  int   = 85
    monthly_expenses: float
    inflation:        float = 6.0
    current_savings:  float = 0
    return_pre:       float = 12.0
    return_post:      float = 7.0

@router.post("/retirement", dependencies=[Depends(require_plan("retirement"))])
async def retirement(body: RetirementRequest, request: Request):
    uid    = request.state.uid
    result = RetirementEngine.calculate(body.model_dump())
    try:
        EngineDataService.save_retirement_result(uid, body.model_dump(), result)
    except Exception as e:
        logger.warning(f"Could not save retirement result for {uid}: {e}")
    return result


@router.get("/retirement/history", dependencies=[Depends(require_plan("retirement"))])
async def retirement_history(request: Request):
    uid = request.state.uid
    return {"history": EngineDataService.get_retirement_history(uid)}


# ════════════════════════════════════════════════════════════
# PRO ENGINES
# ════════════════════════════════════════════════════════════

class StockRequest(BaseModel):
    symbol: str

@router.post("/stock-analysis", dependencies=[Depends(require_plan("stock-analysis"))])
async def stock_analysis(body: StockRequest, request: Request):
    uid    = request.state.uid
    result = await StockAnalysisEngine.analyze(body.symbol.upper().strip(), uid=uid)
    return result


@router.get("/stock-analysis/history", dependencies=[Depends(require_plan("stock-analysis"))])
async def stock_analysis_history(request: Request):
    uid = request.state.uid
    return {"history": EngineDataService.get_stock_analysis_history(uid)}


class PortfolioRequest(BaseModel):
    amount:    float
    risk:      str   = "moderate"
    horizon:   int   = 5

@router.post("/portfolio", dependencies=[Depends(require_plan("portfolio"))])
async def portfolio(body: PortfolioRequest, request: Request):
    uid    = request.state.uid
    result = PortfolioEngine.optimize(body.amount, body.risk, body.horizon)
    try:
        EngineDataService.save_portfolio_result(uid, body.model_dump(), result)
    except Exception as e:
        logger.warning(f"Could not save portfolio result for {uid}: {e}")
    return result


@router.get("/portfolio/history", dependencies=[Depends(require_plan("portfolio"))])
async def portfolio_history(request: Request):
    uid = request.state.uid
    return {"history": EngineDataService.get_portfolio_history(uid)}


class InvestmentAdviceRequest(BaseModel):
    investment_amount: float

@router.post("/investment-advice", dependencies=[Depends(require_plan("portfolio"))])
async def investment_advice(body: InvestmentAdviceRequest, request: Request):
    """
    [NEW] Combines the user's stored risk profile + portfolio optimizer
    into personalized advice. Was previously built (engines/investment_engine.py)
    but never wired to a route.
    """
    uid    = request.state.uid
    result = InvestmentEngine.get_personalized_advice(uid, body.investment_amount)
    try:
        EngineDataService.save_investment_advice(uid, result)
    except Exception as e:
        logger.warning(f"Could not save investment advice for {uid}: {e}")
    return result


@router.get("/investment-advice/history", dependencies=[Depends(require_plan("portfolio"))])
async def investment_advice_history(request: Request):
    uid = request.state.uid
    return {"history": EngineDataService.get_investment_advice_history(uid)}


@router.get("/global-events", dependencies=[Depends(require_plan("global-events"))])
async def global_events(request: Request):
    result = await GlobalEventEngine.get_events()
    return result
