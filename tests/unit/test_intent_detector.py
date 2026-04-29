from app.ai.intent_detector import IntentDetector


def test_intent_detector_support():
    detector = IntentDetector()
    assert detector.detect("I need help with my refund issue") == "support"


def test_intent_detector_booking():
    detector = IntentDetector()
    assert detector.detect("I want to buy a ticket for this event") == "booking"
