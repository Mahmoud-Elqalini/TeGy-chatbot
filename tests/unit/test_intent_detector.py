import asyncio
from app.ai.intent_detector import IntentDetector


def test_intent_detector_support():
    detector = IntentDetector()
    intent, confidence = detector._rule_based_detect("I need help with my refund issue")
    assert "support" in intent
    assert confidence >= 0.5


def test_intent_detector_booking():
    detector = IntentDetector()
    intent, confidence = detector._rule_based_detect("I want to buy a ticket and reserve a seat")
    assert intent == "booking"
    assert confidence >= 0.8
