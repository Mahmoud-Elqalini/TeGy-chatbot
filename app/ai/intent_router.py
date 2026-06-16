from __future__ import annotations

import logging
from typing import TypedDict, Literal
from app.ai.intent_detector import IntentResult

logger = logging.getLogger(__name__)

class RoutingDecision(TypedDict):
    """Structured decision for intent routing."""
    intent: str
    confidence: float
    route: Literal["fast_path", "llm_path", "fallback_path"]
    is_uncertain: bool

class IntentRouter:
    """
    The IntentRouter decides the processing strategy based on intent and confidence.
    It separates the classification logic from the orchestration logic.
    """

    def __init__(self, high_confidence_threshold: float = 0.8, medium_confidence_threshold: float = 0.5):
        self.high_threshold = high_confidence_threshold
        self.medium_threshold = medium_confidence_threshold

    def route(self, result: IntentResult) -> RoutingDecision:
        """
        Takes an IntentResult and determines the best routing path.
        """
        intent = result["intent"]
        confidence = result["confidence"]
        source = result["source"]

        decision: RoutingDecision = {
            "intent": intent,
            "confidence": confidence,
            "route": "llm_path", # Default
            "is_uncertain": False
        }

        # 1. Evaluate Confidence & Source
        if confidence >= self.high_threshold:
            decision["route"] = "fast_path" if intent in {"booking", "greeting"} else "llm_path"
        elif confidence >= self.medium_threshold:
            decision["is_uncertain"] = True
            decision["route"] = "llm_path"
        else:
            decision["route"] = "fallback_path"

        # 2. Intent-specific overrides
        if intent == "greeting":
            decision["route"] = "fast_path"
        elif intent == "general":
            decision["route"] = "llm_path"
        elif intent.startswith("support_") and confidence >= self.high_threshold:
            # High confidence support still goes to LLM but marked for knowledge enhancement
            decision["route"] = "llm_path"

        # 3. Log the decision for observability
        logger.info(
            "intent.decision",
            extra={
                "intent.router.intent": intent,
                "intent.router.confidence": confidence,
                "intent.router.route": decision["route"],
                "intent.router.source": source,
                "intent.router.is_uncertain": decision["is_uncertain"]
            }
        )

        return decision
