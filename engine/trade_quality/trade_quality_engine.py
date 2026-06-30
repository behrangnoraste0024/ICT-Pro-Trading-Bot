from __future__ import annotations

from models.market_context import MarketContext
from models.trade_quality_event import TradeQualityEvent


class TradeQualityEngine:
    def __init__(
        self,
        minimum_rr: float = 2.0,
        minimum_quality_score: int = 85,
        min_risk_percent: float = 0.0005,
        max_risk_percent: float = 0.02,
    ):
        self.minimum_rr = minimum_rr
        self.minimum_quality_score = minimum_quality_score
        self.min_risk_percent = min_risk_percent
        self.max_risk_percent = max_risk_percent

    def detect(self, context: MarketContext) -> MarketContext:
        self._reset_context(context)

        if context.trade_plan_status != "PLANNED":
            self._mark_no_planned_trade(context)
            return context

        score = 0
        reasons: list[str] = []
        blockers: list[str] = []
        risk_percent = None
        reward_percent = None

        if self._is_complete(context):
            score += 15
            reasons.append("TRADE_PLAN_COMPLETE")
        else:
            blockers.append("INCOMPLETE_TRADE_PLAN")

        entry_price = context.planned_entry_price
        if entry_price is None or entry_price <= 0:
            blockers.append("INVALID_ENTRY_PRICE")
        elif context.planned_risk is not None and context.planned_reward is not None:
            risk_percent = context.planned_risk / entry_price
            reward_percent = context.planned_reward / entry_price

        risk_reward = context.planned_risk_reward
        if risk_reward is not None and risk_reward >= self.minimum_rr:
            score += 35
            reasons.append("RR_OK")
        else:
            blockers.append("RR_TOO_LOW")

        if risk_percent is not None:
            if risk_percent < self.min_risk_percent:
                blockers.append("RISK_TOO_TIGHT")
            elif risk_percent > self.max_risk_percent:
                blockers.append("RISK_TOO_WIDE")
            else:
                score += 25
                reasons.append("RISK_DISTANCE_OK")

        if reward_percent is not None and reward_percent > 0:
            score += 15
            reasons.append("REWARD_DISTANCE_OK")
        else:
            blockers.append("INVALID_REWARD_DISTANCE")

        if context.trade_direction in ("BULLISH", "BEARISH"):
            score += 10
            reasons.append("DIRECTION_OK")
        else:
            blockers.append("INVALID_TRADE_DIRECTION")

        if blockers:
            status = "REJECTED"
        elif score >= self.minimum_quality_score:
            status = "APPROVED"
        else:
            status = "REJECTED"
            blockers.append("QUALITY_SCORE_TOO_LOW")

        event = TradeQualityEvent(
            status=status,
            score=score,
            reasons=reasons,
            blockers=blockers,
            risk_percent=risk_percent,
            reward_percent=reward_percent,
            risk_reward=risk_reward,
        )

        context.trade_quality = event
        context.trade_quality_status = status
        context.trade_quality_score = score
        context.trade_quality_blockers = blockers
        context.trade_quality_reasons = reasons
        self._update_debug(context)
        return context

    def _reset_context(self, context: MarketContext) -> None:
        context.trade_quality = None
        context.trade_quality_status = "REJECTED"
        context.trade_quality_score = 0
        context.trade_quality_blockers = []
        context.trade_quality_reasons = []

    def _is_complete(self, context: MarketContext) -> bool:
        required_values = [
            context.planned_entry_price,
            context.planned_stop_loss,
            context.planned_take_profit,
            context.planned_risk,
            context.planned_reward,
            context.planned_risk_reward,
        ]
        return all(value is not None for value in required_values)

    def _mark_no_planned_trade(self, context: MarketContext) -> None:
        context.trade_quality = None
        context.trade_quality_status = "REJECTED"
        context.trade_quality_score = 0
        context.trade_quality_blockers = ["NO_PLANNED_TRADE"]
        context.trade_quality_reasons = []
        self._update_debug(context)

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["trade_quality_status"] = context.trade_quality_status
        context.debug["trade_quality_score"] = context.trade_quality_score
        context.debug["trade_quality_blockers"] = context.trade_quality_blockers
        context.debug["trade_quality_reasons"] = context.trade_quality_reasons
