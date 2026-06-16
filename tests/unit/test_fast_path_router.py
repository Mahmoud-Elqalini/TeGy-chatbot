"""
Unit tests for FastPathRouter.

Covers:
- All four fast-path types match (greeting, identity, thanks, goodbye)
- Arabic and English variants both match
- Compound messages (social + booking intent) do NOT match
- Empty / whitespace-only input does NOT match
- Returned FastPathResult has correct structure and token savings
"""
from __future__ import annotations

import pytest

from app.ai.fast_path_router import FastPathRouter, FastPathResult


@pytest.fixture
def router() -> FastPathRouter:
    """Router with explicit baselines to make assertions deterministic."""
    return FastPathRouter(planner_avg_tokens=800, renderer_avg_tokens=600)


# ---------------------------------------------------------------------------
# Greeting
# ---------------------------------------------------------------------------


class TestGreeting:
    def test_arabic_marhaba(self, router: FastPathRouter):
        result = router.match("مرحبا")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_ahlan(self, router: FastPathRouter):
        result = router.match("اهلا")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_salam_alaykum(self, router: FastPathRouter):
        result = router.match("السلام عليكم")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_hai(self, router: FastPathRouter):
        result = router.match("هاي")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_salam(self, router: FastPathRouter):
        result = router.match("سلام")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_sabah_khayr(self, router: FastPathRouter):
        result = router.match("صباح الخير")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_arabic_masaa_khayr(self, router: FastPathRouter):
        result = router.match("مساء الخير")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_english_hello(self, router: FastPathRouter):
        result = router.match("hello")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_english_hi(self, router: FastPathRouter):
        result = router.match("hi")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_english_hey(self, router: FastPathRouter):
        result = router.match("hey!")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_english_good_morning(self, router: FastPathRouter):
        result = router.match("Good morning")
        assert result is not None
        assert result.fast_path_type == "greeting"

    def test_response_is_not_empty(self, router: FastPathRouter):
        result = router.match("مرحبا")
        assert result is not None
        assert len(result.response) > 0

    def test_response_contains_brand(self, router: FastPathRouter):
        result = router.match("hello")
        assert result is not None
        assert "TeGy" in result.response


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_arabic_meen_enta(self, router: FastPathRouter):
        result = router.match("مين انت")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_arabic_enta_meen(self, router: FastPathRouter):
        result = router.match("انت مين")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_arabic_eih_ismak(self, router: FastPathRouter):
        result = router.match("ايه اسمك")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_english_who_are_you(self, router: FastPathRouter):
        result = router.match("who are you")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_english_what_is_your_name(self, router: FastPathRouter):
        result = router.match("what is your name")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_english_whats_your_name(self, router: FastPathRouter):
        result = router.match("what's your name?")
        assert result is not None
        assert result.fast_path_type == "identity"

    def test_english_tell_me_about_yourself(self, router: FastPathRouter):
        result = router.match("tell me about yourself")
        assert result is not None
        assert result.fast_path_type == "identity"


# ---------------------------------------------------------------------------
# Thanks
# ---------------------------------------------------------------------------


class TestThanks:
    def test_arabic_shukran(self, router: FastPathRouter):
        result = router.match("شكرا")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_arabic_mutashakir(self, router: FastPathRouter):
        result = router.match("متشكر")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_arabic_mamnun(self, router: FastPathRouter):
        result = router.match("ممنون")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_arabic_tislam(self, router: FastPathRouter):
        result = router.match("تسلم")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_english_thank_you(self, router: FastPathRouter):
        result = router.match("thank you")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_english_thanks(self, router: FastPathRouter):
        result = router.match("thanks")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_english_thx(self, router: FastPathRouter):
        result = router.match("thx")
        assert result is not None
        assert result.fast_path_type == "thanks"

    def test_english_cheers(self, router: FastPathRouter):
        result = router.match("cheers")
        assert result is not None
        assert result.fast_path_type == "thanks"


# ---------------------------------------------------------------------------
# Goodbye
# ---------------------------------------------------------------------------


class TestGoodbye:
    def test_arabic_maa_salama(self, router: FastPathRouter):
        result = router.match("مع السلامة")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_arabic_yalla_bye(self, router: FastPathRouter):
        result = router.match("يلا باي")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_arabic_wada3an(self, router: FastPathRouter):
        result = router.match("وداعا")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_english_bye(self, router: FastPathRouter):
        result = router.match("bye")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_english_goodbye(self, router: FastPathRouter):
        result = router.match("goodbye")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_english_see_you(self, router: FastPathRouter):
        result = router.match("see you")
        assert result is not None
        assert result.fast_path_type == "goodbye"

    def test_english_take_care(self, router: FastPathRouter):
        result = router.match("take care")
        assert result is not None
        assert result.fast_path_type == "goodbye"


# ---------------------------------------------------------------------------
# No-match cases — these MUST return None
# ---------------------------------------------------------------------------


class TestNoMatch:
    """Compound or substantive messages must NOT match fast-path."""

    def test_hi_plus_booking_intent(self, router: FastPathRouter):
        """Greeting + booking intent — too complex for fast path."""
        result = router.match("hi, I need to book a ticket")
        assert result is None

    def test_booking_only(self, router: FastPathRouter):
        result = router.match("أريد حجز تذكرة")
        assert result is None

    def test_event_search(self, router: FastPathRouter):
        result = router.match("ما هي الفعاليات المتاحة هذا الأسبوع؟")
        assert result is None

    def test_cancel_booking(self, router: FastPathRouter):
        result = router.match("أريد إلغاء حجزي رقم 1234")
        assert result is None

    def test_support_question(self, router: FastPathRouter):
        result = router.match("لدي مشكلة في الدفع")
        assert result is None

    def test_empty_string(self, router: FastPathRouter):
        result = router.match("")
        assert result is None

    def test_whitespace_only(self, router: FastPathRouter):
        result = router.match("   ")
        assert result is None


# ---------------------------------------------------------------------------
# Metrics — token savings
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_saved_planner_tokens(self, router: FastPathRouter):
        result = router.match("مرحبا")
        assert result is not None
        assert result.saved_planner_tokens == 800

    def test_saved_renderer_tokens(self, router: FastPathRouter):
        result = router.match("مرحبا")
        assert result is not None
        assert result.saved_renderer_tokens == 600

    def test_saved_total_tokens(self, router: FastPathRouter):
        result = router.match("مرحبا")
        assert result is not None
        assert result.saved_total_tokens == 1400  # 800 + 600

    def test_end_to_end_ms_is_non_negative(self, router: FastPathRouter):
        result = router.match("hello")
        assert result is not None
        assert result.end_to_end_ms >= 0.0

    def test_end_to_end_ms_is_fast(self, router: FastPathRouter):
        """Fast-path should complete well under 50 ms — it's pure regex."""
        result = router.match("hello")
        assert result is not None
        assert result.end_to_end_ms < 50.0

    def test_result_is_frozen(self, router: FastPathRouter):
        """FastPathResult must be immutable (frozen dataclass)."""
        result = router.match("hello")
        assert result is not None
        with pytest.raises((AttributeError, TypeError)):
            result.response = "hacked"  # type: ignore[misc]
