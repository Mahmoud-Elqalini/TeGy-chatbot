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
            "subscription", "checkout", "receipt", "paid", "fees", "دفع", "فلوس", "رصيد", "حساب", "سعر", "تكلفة", "استرجاع", "خصم"
        },
        "technical": {
            "bug", "error", "login", "app", "website", "broken", "technical", "fail", 
            "crash", "slow", "down", "password", "access", "connection", "مشكلة", "تطبيق", "ابلكيشن", "موقع", "باسورد", "تسجيل", "عطل", "مش شغال", "مش بيفتح"
        },
        "event": {
            "location", "date", "time", "event", "place", "directions", "where", "when", 
            "schedule", "agenda", "venue", "map", "address", "تفاصيل", "مكان", "وقت", "موعد", "خريطة", "عنوان", "موقع"
        },
    }
    SUPPORT_HINTS = {"support", "help", "problem", "issue", "cancel", "assistant", "manager", "representative", "دعم", "مساعدة", "مشكلة", "الغاء"}
    BOOKING_HINTS = {"ticket", "booking", "reserve", "seat", "buy", "purchase", "order", "reservation", "confirm", "حجز", "تذكرة", "تذاكر", "احجز", "كرسي", "شراء", "اشتري", "تأكيد"}
    DISCOVER_HINTS = {"search", "find", "looking", "discover", "explore", "show", "events", "concert", "party", "match", "دور", "ابحث", "حفلة", "ماتش", "خروجة", "فعاليات", "ايفنت", "ايفنتات", "عرض", "حفلات", "مسرحية"}
    MANAGE_HINTS = {"my bookings", "my tickets", "history", "past", "upcoming", "حجوزاتي", "تذاكري", "سابقة", "قادمة", "الغي", "تعديل"}
    GREETING_HINTS = {"hi", "hello", "hey", "hola", "هاي", "سلام", "اهلا", "مرحبا", "صباح", "مساء", "اسمك"}

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
            confidence = 0.9 if any(p in normalized for p in ["book a ticket", "buy a ticket", "reserve a seat", "عايز احجز", "تذكرتين", "احجز تذكرة"]) else 0.85
            return "booking", confidence

        # Check for Discover Hints
        if tokens & self.DISCOVER_HINTS:
            return "discover", 0.85

        # Check for Manage Hints
        if tokens & self.MANAGE_HINTS:
            return "manage_booking", 0.85

        # Check for Greeting Hints
        if tokens & self.GREETING_HINTS:
            return "greeting", 0.98

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
                "source": "rule",
                "tokens": 0
            }

        # Fallback to LLM if needed (uncertain or general)
        if (rule_confidence < 0.6 or rule_intent == "general") and self.response_generator:
            logger.info("intent.detector.llm_fallback", rule_intent=rule_intent, rule_confidence=rule_confidence)
            try:
                llm_intent, tokens = await self._llm_detect(content, history)
                # LLM result is realistic but not perfect
                return {
                    "intent": llm_intent,
                    "confidence": 0.85, 
                    "source": "llm",
                    "tokens": tokens
                }
            except Exception as exc:
                logger.error("intent.detector.llm_failed", error=str(exc))
                return {
                    "intent": rule_intent,
                    "confidence": rule_confidence,
                    "source": "rule",
                    "tokens": 0
                }

        # Medium confidence match
        return {
            "intent": rule_intent,
            "confidence": rule_confidence,
            "source": "rule",
            "tokens": 0
        }

    async def _llm_detect(self, content: str, history: list[dict] | None = None) -> tuple[str, int]:
        """
        Deterministic LLM classification.
        """
        prompt = f"""
        Classify the user message into exactly ONE category:
        - discover
        - booking
        - manage_booking
        - support_billing
        - support_technical
        - support_event
        - greeting
        - general

        Message: "{content}"
        
        Return ONLY the label. No explanation.
        """
        
        try:
            response = await self.response_generator.generate_simple(prompt)
            detected = response.content.strip().lower()
            tokens_used = response.prompt_tokens + response.completion_tokens
            
            valid_intents = {"discover", "booking", "manage_booking", "support_billing", "support_technical", "support_event", "greeting", "general"}
            if detected in valid_intents:
                return detected, tokens_used
            
            # Map common LLM variations if any
            if "ticket" in detected or "reserve" in detected: return "booking", tokens_used
            if "bill" in detected or "pay" in detected: return "support_billing", tokens_used
            if "find" in detected or "search" in detected: return "discover", tokens_used
            
            return "general", tokens_used
        except Exception:
            raise
