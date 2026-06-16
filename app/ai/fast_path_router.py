"""
Fast Path Router — lightweight pre-LLM interception layer.

Matches social/meta intents that require no reasoning, planning, or tool calls.
When a message matches, the caller MUST skip both Planner and Renderer and return
the predefined response directly.

Design constraints:
- Zero LLM calls — pure regex matching, O(1) per message.
- Immutable: patterns and responses are compiled at import time.
- Returns None on no match so the caller falls through gracefully.
- Fully typed; no dynamic dispatch.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal, Optional

from app.core.observability import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

FastPathType = Literal["greeting", "identity", "thanks", "goodbye"]


@dataclass(frozen=True, slots=True)
class FastPathResult:
    """Returned when a message is matched by the Fast Path Router."""

    response: str
    fast_path_type: FastPathType
    # Metrics — always zero tokens since no LLM is invoked
    saved_planner_tokens: int
    saved_renderer_tokens: int
    saved_total_tokens: int
    end_to_end_ms: float = 0.0


# ---------------------------------------------------------------------------
# Pattern registry — compiled once at module load
# ---------------------------------------------------------------------------

_PATTERN_MAP: list[tuple[FastPathType, re.Pattern[str]]] = [
    # ── Greeting ──────────────────────────────────────────────────────────
    # Arabic: مرحبا، اهلا، هاي، سلام، السلام عليكم، صباح الخير، مساء الخير
    # English: hello, hi, hey, howdy, greetings, good morning/evening/afternoon
    (
        "greeting",
        re.compile(
            r"""
            ^                                       # must start here
            (?:
                # Arabic greetings
                (?:السلام\s+عليكم|سلام\s+عليكم)|   # formal Islamic greeting
                مرحبا? |                            # مرحب / مرحبا
                اهلا? (?:\s+وسهلا?)? |              # اهل / اهلا / اهلا وسهلا
                هاي |                               # هاي
                سلام |                              # سلام
                (?:صباح|مساء)\s+(?:الخير|النور)|   # صباح/مساء الخير/النور
                ازيك | عامل\s+إيه |                 # colloquial how-are-you
                # English greetings
                h(?:ello|owdy|ey|i) |               # hello, howdy, hey, hi
                good\s+(?:morning|afternoon|evening|day) |
                greetings? | yo | sup | what'?s\s+up
            )
            [\s!،,.؟?]*                             # optional trailing punctuation
            $                                       # nothing meaningful after
            """,
            re.VERBOSE | re.IGNORECASE | re.UNICODE,
        ),
    ),
    # ── Identity ──────────────────────────────────────────────────────────
    # Arabic: مين انت / انت مين / ايه اسمك / من أنت / إيه اسمك
    # English: who are you / what are you / your name / tell me about yourself
    (
        "identity",
        re.compile(
            r"""
            (?:
                # Arabic identity questions
                (?:مين|من)\s+(?:انت|أنت)|           # مين انت / من انت
                (?:انت|أنت)\s+(?:مين|من)|           # انت مين
                (?:ايه|إيه|ما)\s+اسمك |             # ايه اسمك
                اسمك\s+(?:ايه|إيه|ما|ه) |           # اسمك ايه
                عرف\s+(?:نفسك|بنفسك) |              # عرف نفسك
                # English identity questions
                who\s+are\s+you |
                what\s+are\s+you |
                (?:what'?s|what\s+is)\s+your\s+name |
                tell\s+me\s+about\s+yourself |
                introduce\s+yourself
            )
            """,
            re.VERBOSE | re.IGNORECASE | re.UNICODE,
        ),
    ),
    # ── Thanks ────────────────────────────────────────────────────────────
    # Arabic: شكرا / متشكر / ممنون / تسلم / مشكور
    # English: thank you / thanks / thx / ty / much appreciated
    (
        "thanks",
        re.compile(
            r"""
            ^
            (?:
                # Arabic thanks
                شكر(?:ا|ًا|اً)? |                  # شكرا / شكر
                متشكر |
                ممنون |
                مشكور |
                تسلم |
                يسلمو |
                جزاك\s+الله\s+خير |
                بارك\s+الله\s+فيك |
                # English thanks
                thank\s+you |
                thanks? |
                thx | ty | thnx |
                much\s+appreciated |
                appreciate\s+(?:it|that) |
                cheers
            )
            [\s!،,.؟?]*
            $
            """,
            re.VERBOSE | re.IGNORECASE | re.UNICODE,
        ),
    ),
    # ── Goodbye ───────────────────────────────────────────────────────────
    # Arabic: مع السلامة / باي / وداعا / تصبح على خير / يلا باي
    # English: bye / goodbye / see you / later / take care
    (
        "goodbye",
        re.compile(
            r"""
            ^
            (?:
                # Arabic goodbye
                مع\s+السلامة |
                (?:يلا\s+)?باي |                    # باي / يلا باي
                وداعاً? |                           # وداعا / وداعاً
                تصبح\s+على\s+خير |
                لقاء\s+قريب |
                إلى\s+اللقاء |
                # English goodbye
                bye(?:\s*bye)? |                    # bye / bye bye
                good\s*bye |
                see\s+(?:you|ya)(?:\s+later)? |
                later |
                take\s+care |
                cya | ttyl | gtg | gotta\s+go
            )
            [\s!،,.؟?]*
            $
            """,
            re.VERBOSE | re.IGNORECASE | re.UNICODE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# On-brand responses — Arabic-first, friendly, TeGy-branded
# ---------------------------------------------------------------------------

_RESPONSES: dict[FastPathType, str] = {
    "greeting": "أهلاً وسهلاً! أنا TeGy، مساعدك الذكي 🎟️\nأقدر أساعدك في الحجز، الاستفسار عن الفعاليات، أو إدارة تذاكرك. إزاي أقدر أساعدك؟ 😊",
    "identity": "أنا TeGy، مساعد ذكي متخصص في حجز التذاكر والفعاليات 🎟️\nأقدر أساعدك تحجز تذاكرك، تشوف الفعاليات المتاحة، أو تدير حجوزاتك بسهولة. كيف أقدر أساعدك؟",
    "thanks": "العفو! يسعدني مساعدتك دايمًا 😊\nفي حاجة تانية أقدر أساعدك فيها؟",
    "goodbye": "مع السلامة! 👋\nلو احتجت أي مساعدة في الحجز أو الفعاليات، أنا هنا دايمًا.",
}

# ---------------------------------------------------------------------------
# Token baselines (used for savings estimation)
# ---------------------------------------------------------------------------

# Fallback averages used when no real baseline is available from the token tracker.
_PLANNER_AVG_TOKENS: int = 800
_RENDERER_AVG_TOKENS: int = 600


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class FastPathRouter:
    """
    Lightweight pre-LLM routing layer.

    Call ``match()`` before invoking the Planner. If it returns a
    ``FastPathResult``, return it directly and skip ALL LLM calls.
    If it returns ``None``, proceed to the normal LLM path.

    Thread-safe: all state is module-level and immutable after import.
    """

    def __init__(
        self,
        planner_avg_tokens: int = _PLANNER_AVG_TOKENS,
        renderer_avg_tokens: int = _RENDERER_AVG_TOKENS,
    ) -> None:
        self._planner_avg = planner_avg_tokens
        self._renderer_avg = renderer_avg_tokens

    def match(self, message: str) -> Optional[FastPathResult]:
        """
        Attempt to match *message* against all fast-path patterns.

        Returns a ``FastPathResult`` on match, ``None`` on miss.
        The caller is responsible for logging / metrics propagation.

        Args:
            message: Raw user message string (stripped or unstripped — both work).
        """
        t0 = time.perf_counter()
        normalized = message.strip()

        for path_type, pattern in _PATTERN_MAP:
            if pattern.search(normalized):
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
                logger.info(
                    "fast_path.matched",
                    fast_path_type=path_type,
                    match_ms=elapsed_ms,
                )
                return FastPathResult(
                    response=_RESPONSES[path_type],
                    fast_path_type=path_type,
                    saved_planner_tokens=self._planner_avg,
                    saved_renderer_tokens=self._renderer_avg,
                    saved_total_tokens=self._planner_avg + self._renderer_avg,
                    end_to_end_ms=elapsed_ms,
                )

        logger.debug("fast_path.miss", message_preview=normalized[:60])
        return None
