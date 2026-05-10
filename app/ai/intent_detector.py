from __future__ import annotations

import re
from typing import Optional, Union, Any, TypedDict, Literal
from app.core.observability import get_logger

logger = get_logger(__name__)

class IntentResult(TypedDict):
    """Structured result for intent classification."""
    intent: str
    confidence: float
    source: Literal["rule", "llm"]

class IntentDetector:
    """
    Hybrid Intent Classification System.
    Uses fast rule-based matching with confidence scoring and falls back to LLM 
    for ambiguous or complex cases. Optimized for performance and cost.
    """

    # Categories and keywords to look for (with lightweight synonym expansion)
    SUPPORT_MAP = {
        "billing": {
            "refund", "payment", "price", "charge", "invoice", "cost", "bill", "money", 
            "subscription", "checkout", "receipt", "paid", "fees"
        },
        "technical": {
            "bug", "error", "login", "app", "website", "broken", "technical", "fail", 
            "crash", "slow", "down", "password", "access", "connection"
        },
        "event": {
            "location", "date", "time", "event", "place", "directions", "where", "when", 
            "schedule", "agenda", "venue", "map", "address"
        },
    }
    SUPPORT_HINTS = {"support", "help", "problem", "issue", "cancel", "assistant", "manager", "representative"}
    BOOKING_HINTS = {"ticket", "booking", "reserve", "seat", "buy", "purchase", "order", "reservation", "confirm"}
    GREETING_HINTS = {"hi", "hello", "hey", "hola", "هاي", "سلام", "اهلا", "مرحبا", "صباح", "مساء"}

    def __init__(self, response_generator: Optional[Any] = None):
        """
        Initializes the IntentDetector.
        """
        self.response_generator = response_generator

    def _get_tokens(self, content: str) -> set[str]:
        """
        Extracts words using regex for better tokenization.
        """
        return set(re.findall(r"\b\w+\b", content.lower()))

    def _rule_based_detect(self, content: str) -> tuple[str, float]:
        """
        Fast rule-based detection with improved confidence scoring.
        Uses word overlap and phrase detection.
        """
        normalized = content.lower()
        tokens = self._get_tokens(normalized)
        if not tokens:
            return "general", 0.0

        # Check for Support Categories
        for category, hints in self.SUPPORT_MAP.items():
            intersection = tokens & hints
            if intersection:
                # Rule: Exact match on high-value terms OR multiple matches
                confidence = 0.9 if len(intersection) >= 2 else 0.75
                # Boost if specific phrases are present
                if f"support {category}" in normalized or f"{category} problem" in normalized:
                    confidence = min(1.0, confidence + 0.15)
                return f"support_{category}", confidence

        # Check for General Support Hints
        if tokens & self.SUPPORT_HINTS:
            return "support_general", 0.8

        # Check for Booking Hints
        if tokens & self.BOOKING_HINTS:
            confidence = 0.9 if any(p in normalized for p in ["book a ticket", "buy a ticket", "reserve a seat"]) else 0.85
            return "booking", confidence

        # Check for Greeting Hints
        if tokens & self.GREETING_HINTS:
            return "general", 0.95

        # Default fallback
        return "general", 0.2

    async def detect_complex(self, content: str, history: list[dict] | None = None) -> IntentResult:
        """
        Hybrid detection logic with refined confidence thresholds.
        """
        rule_intent, rule_confidence = self._rule_based_detect(content)
        
        # High confidence match (trust rule)
        if rule_confidence >= 0.85:
            logger.debug("intent.detector.rule_high", intent=rule_intent, confidence=rule_confidence)
            return {
                "intent": rule_intent,
                "confidence": rule_confidence,
                "source": "rule"
            }

        # Fallback to LLM if needed (uncertain or general)
        if (rule_confidence < 0.6 or rule_intent == "general") and self.response_generator:
            logger.info("intent.detector.llm_fallback", rule_intent=rule_intent, rule_confidence=rule_confidence)
            try:
                llm_intent = await self._llm_detect(content, history)
                # LLM result is realistic but not perfect
                return {
                    "intent": llm_intent,
                    "confidence": 0.85, 
                    "source": "llm"
                }
            except Exception as exc:
                logger.error("intent.detector.llm_failed", error=str(exc))
                return {
                    "intent": rule_intent,
                    "confidence": rule_confidence,
                    "source": "rule"
                }

        # Medium confidence match
        return {
            "intent": rule_intent,
            "confidence": rule_confidence,
            "source": "rule"
        }

    async def _llm_detect(self, content: str, history: list[dict] | None = None) -> str:
        """
        Deterministic LLM classification.
        """
        prompt = f"""
        Classify the user message into exactly ONE category:
        - booking
        - support_billing
        - support_technical
        - support_event
        - general

        Message: "{content}"
        
        Return ONLY the label. No explanation.
        """
        
        try:
            response = await self.response_generator.generate_simple(prompt)
            detected = response.strip().lower()
            
            valid_intents = {"booking", "support_billing", "support_technical", "support_event", "general"}
            if detected in valid_intents:
                return detected
            
            # Map common LLM variations if any
            if "ticket" in detected or "reserve" in detected: return "booking"
            if "bill" in detected or "pay" in detected: return "support_billing"
            
            return "general"
        except Exception:
            raise


