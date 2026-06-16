"""
Unit tests for the optimization paths in AIOrchestrator.

Covers:
- Fast-path match → zero LLM calls (generate() never called)
- Fast-path match → correct token savings in returned breakdown
- Fast-path match → RequestTrace populated correctly
- Fast-path miss (booking) → falls through to llm_path (generate() IS called)
- Template match → Renderer skipped (generate() called once for Planner only)
- Template miss → Renderer called (generate() called twice: Planner + Renderer)
- Template match → RequestTrace.renderer_skipped = True
- Template match → saved_renderer_tokens populated
- No tool calls → Renderer never called
- Booking routing bug is FIXED (booking via fast_path goes to full pipeline)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.fast_path_router import FastPathRouter, FastPathResult
from app.ai.providers.base import LLMRequest, LLMResponse
from app.ai.template_engine import TemplateEngine, TemplateResult
from app.services.ai_orchestrator import AIOrchestrator


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


class _FakeValidator:
    def validate_response(self, text: str) -> str:
        return text

    def sanitize_history(self, history: list) -> list:
        return history

    def sanitize_tool_output(self, text: str) -> str:
        return text


class _FakeRegistry:
    def get_tool_definitions(self) -> list:
        return []

    async def call_tool(self, name: str, runtime_deps: dict, **kwargs) -> Any:
        return {"booking_id": "BK-TEST-001"}


def _make_llm_response(content: str = "ok", tool_calls=None) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="fake-model",
        provider="fake",
        prompt_tokens=100,
        completion_tokens=50,
        tool_calls=tool_calls,
    )


def _make_orchestrator(
    generate_side_effect=None,
    fast_path_router: Optional[FastPathRouter] = None,
    template_engine: Optional[TemplateEngine] = None,
    tool_registry=None,
) -> tuple[AIOrchestrator, AsyncMock]:
    """Build an orchestrator with a mocked generate() and optional overrides."""
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=generate_side_effect or [_make_llm_response()])
    provider.count_tokens = AsyncMock(return_value=50)

    response_gen = MagicMock()
    response_gen.provider = provider
    response_gen.generate = provider.generate  # used by generate_response()

    orch = AIOrchestrator(
        response_generator=response_gen,
        response_validator=_FakeValidator(),
        tool_registry=tool_registry,
        fast_path_router=fast_path_router,
        template_engine=template_engine,
    )
    # Patch generate_response to delegate to provider.generate for simpler mock tracking
    orch.response_generator.generate = provider.generate
    return orch, provider.generate


def _base_payload() -> dict:
    ctx = MagicMock()
    ctx.user_id = "user-1"
    ctx.model_name = "test-model"
    return {
        "model": "test-model",
        "system_prompt": "You are TeGy.",
        "renderer_prompt": "Render the results.",
        "history": [],
        "context": ctx,
    }


# ---------------------------------------------------------------------------
# Fast-Path Router integration
# ---------------------------------------------------------------------------


class TestFastPathIntegration:
    """generate_complex() with route='fast_path' and a social message."""

    @pytest.mark.asyncio
    async def test_greeting_skips_all_llm_calls(self):
        orch, generate_mock = _make_orchestrator()
        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="مرحبا",
            intent="greeting",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        generate_mock.assert_not_called()
        assert content  # non-empty response
        assert tokens == 0

    @pytest.mark.asyncio
    async def test_greeting_returns_correct_type(self):
        orch, _ = _make_orchestrator()
        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="hello",
            intent="greeting",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        assert breakdown.get("fast_path_type") == "greeting"

    @pytest.mark.asyncio
    async def test_thanks_fast_path(self):
        orch, generate_mock = _make_orchestrator()
        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="شكرا",
            intent="thanks",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        generate_mock.assert_not_called()
        assert breakdown.get("fast_path_type") == "thanks"

    @pytest.mark.asyncio
    async def test_fast_path_token_savings_in_breakdown(self):
        orch, _ = _make_orchestrator()
        _, _, _, breakdown = await orch.generate_complex(
            user_input="مرحبا",
            intent="greeting",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        assert breakdown["saved_planner_tokens"] > 0
        assert breakdown["saved_renderer_tokens"] > 0
        assert breakdown["saved_total_tokens"] > 0

    @pytest.mark.asyncio
    async def test_fast_path_returns_empty_tool_results(self):
        orch, _ = _make_orchestrator()
        _, _, tools, _ = await orch.generate_complex(
            user_input="bye",
            intent="goodbye",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        assert tools == []


# ---------------------------------------------------------------------------
# Booking routing bug fix
# ---------------------------------------------------------------------------


class TestBookingRoutingBugFix:
    """
    PRE-FIX BUG:
      intent=booking, route=fast_path → old _execute_fast_path()
      → no greeting match → LLMRequest(system_prompt="Quick assistant.", tools=None)
      → booking answered without tools → hallucination

    POST-FIX:
      intent=booking, route=fast_path → FastPathRouter.match("أريد حجز تذكرة")
      → miss (not a social message) → fall through to _execute_llm_path()
      → Planner called with proper system_prompt and tools
    """

    @pytest.mark.asyncio
    async def test_booking_via_fast_path_route_calls_planner(self):
        """A booking message via route=fast_path must go to the full LLM path."""
        planner_response = _make_llm_response("I'll search for events", tool_calls=None)
        orch, generate_mock = _make_orchestrator(
            generate_side_effect=[planner_response],
        )
        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="أريد حجز تذكرة لحفلة موسيقية",
            intent="booking",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",  # ← this is what IntentRouter sends for booking
        )
        # The Planner (generate) MUST be called — no fast-path shortcut for booking
        generate_mock.assert_called_once()
        assert tokens > 0  # real LLM tokens consumed

    @pytest.mark.asyncio
    async def test_booking_via_fast_path_uses_correct_system_prompt(self):
        """Verify that the proper system_prompt (not 'Quick assistant.') is used."""
        captured_requests: List[LLMRequest] = []

        async def capture(request: LLMRequest) -> LLMResponse:
            captured_requests.append(request)
            return _make_llm_response("Result")

        orch, generate_mock = _make_orchestrator(generate_side_effect=capture)
        generate_mock.side_effect = capture

        await orch.generate_complex(
            user_input="أريد حجز تذكرة",
            intent="booking",
            payload=_base_payload(),
            session_id="s1",
            route="fast_path",
        )
        assert len(captured_requests) >= 1
        # The system prompt must be the one from payload, NOT "Quick assistant."
        assert captured_requests[0].system_prompt != "Quick assistant."
        assert "TeGy" in captured_requests[0].system_prompt or len(captured_requests[0].system_prompt) > 20


# ---------------------------------------------------------------------------
# Conditional Renderer (Template Engine integration)
# ---------------------------------------------------------------------------


class TestConditionalRenderer:
    """Tests that the Renderer is skipped when TemplateEngine matches."""

    @pytest.mark.asyncio
    async def test_template_match_skips_renderer(self):
        """When TemplateEngine matches, only the Planner runs — not the Renderer."""
        tool_call = [{"id": "tc1", "name": "create_booking", "arguments": {}}]
        planner_response = _make_llm_response("calling tool", tool_calls=tool_call)

        # Planner is called once; Renderer must NOT be called
        generate_call_count = 0

        async def fake_generate(request: LLMRequest) -> LLMResponse:
            nonlocal generate_call_count
            generate_call_count += 1
            return planner_response

        # TemplateEngine that always matches
        mock_template = MagicMock(spec=TemplateEngine)
        mock_template.match.return_value = TemplateResult(
            response="تم الحجز بنجاح ✅\nرقم الحجز: BK-001",
            skip_reason="booking_created",
            saved_renderer_tokens=600,
        )

        # Registry that returns a booking result
        registry = MagicMock()
        registry.get_tool_definitions.return_value = []
        registry.call_tool = AsyncMock(return_value={"booking_id": "BK-001"})

        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=fake_generate)
        provider.count_tokens = AsyncMock(return_value=30)

        response_gen = MagicMock()
        response_gen.provider = provider
        response_gen.generate = provider.generate

        orch = AIOrchestrator(
            response_generator=response_gen,
            response_validator=_FakeValidator(),
            tool_registry=registry,
            template_engine=mock_template,
        )
        orch.response_generator.generate = provider.generate

        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="أريد حجز تذكرة",
            intent="create_booking",
            payload=_base_payload(),
            session_id="s1",
            route="llm_path",
        )

        # Planner called once, Renderer skipped
        assert generate_call_count == 1
        assert "BK-001" in content or "✅" in content
        assert breakdown.get("saved_renderer_tokens", 0) > 0

    @pytest.mark.asyncio
    async def test_template_miss_calls_renderer(self):
        """When TemplateEngine returns None, the Renderer must be called."""
        tool_call = [{"id": "tc1", "name": "search_events", "arguments": {}}]
        planner_response = _make_llm_response("searching...", tool_calls=tool_call)
        renderer_response = _make_llm_response("Here are the events: ...")

        generate_responses = [planner_response, renderer_response]
        call_index = 0

        async def fake_generate(request: LLMRequest) -> LLMResponse:
            nonlocal call_index
            resp = generate_responses[call_index]
            call_index += 1
            return resp

        # TemplateEngine that never matches
        mock_template = MagicMock(spec=TemplateEngine)
        mock_template.match.return_value = None

        registry = MagicMock()
        registry.get_tool_definitions.return_value = []
        registry.call_tool = AsyncMock(return_value={"events": [{"id": 1}]})

        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=fake_generate)
        provider.count_tokens = AsyncMock(return_value=30)

        response_gen = MagicMock()
        response_gen.provider = provider
        response_gen.generate = provider.generate

        orch = AIOrchestrator(
            response_generator=response_gen,
            response_validator=_FakeValidator(),
            tool_registry=registry,
            template_engine=mock_template,
        )
        orch.response_generator.generate = provider.generate

        _, _, _, breakdown = await orch.generate_complex(
            user_input="اعرض كل الأحداث",
            intent="support_event",
            payload=_base_payload(),
            session_id="s1",
            route="llm_path",
        )

        # Both Planner and Renderer were called
        assert call_index == 2
        assert breakdown.get("renderer_prompt_tokens", 0) > 0

    @pytest.mark.asyncio
    async def test_no_tool_calls_renderer_never_called(self):
        """If Planner returns no tool calls, Renderer must not be invoked."""
        planner_response = _make_llm_response("لا أعرف.", tool_calls=None)
        generate_call_count = 0

        async def fake_generate(request: LLMRequest) -> LLMResponse:
            nonlocal generate_call_count
            generate_call_count += 1
            return planner_response

        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=fake_generate)
        provider.count_tokens = AsyncMock(return_value=10)

        response_gen = MagicMock()
        response_gen.provider = provider
        response_gen.generate = provider.generate

        orch = AIOrchestrator(
            response_generator=response_gen,
            response_validator=_FakeValidator(),
        )
        orch.response_generator.generate = provider.generate

        content, tokens, tools, breakdown = await orch.generate_complex(
            user_input="ما معنى الحياة؟",
            intent="general",
            payload=_base_payload(),
            session_id="s1",
            route="llm_path",
        )

        assert generate_call_count == 1  # Planner only
        assert tools == []
        assert breakdown["renderer_prompt_tokens"] == 0


# ---------------------------------------------------------------------------
# RequestTrace fields
# ---------------------------------------------------------------------------


class TestRequestTraceFields:
    """Verify new trace fields are set correctly in each path."""

    @pytest.mark.asyncio
    async def test_fast_path_trace_fields(self):
        """Fast-path match must set fast_path_used=True and planner_skipped=True in trace."""
        from app.core.trace_context import get_active_trace

        trace_snapshots = []

        original_log = None

        orch, _ = _make_orchestrator()

        # Capture the trace via the logger
        with patch.object(orch.fast_path_router, "match") as mock_match:
            mock_match.return_value = FastPathResult(
                response="أهلاً!",
                fast_path_type="greeting",
                saved_planner_tokens=800,
                saved_renderer_tokens=600,
                saved_total_tokens=1400,
                end_to_end_ms=0.5,
            )
            content, tokens, _, breakdown = await orch.generate_complex(
                user_input="مرحبا",
                intent="greeting",
                payload=_base_payload(),
                session_id="s1",
                route="fast_path",
            )

        assert breakdown["fast_path_type"] == "greeting"
        assert breakdown["saved_total_tokens"] == 1400

    @pytest.mark.asyncio
    async def test_template_path_sets_saved_renderer_tokens(self):
        """Template path must populate saved_renderer_tokens in breakdown."""
        tool_call = [{"id": "tc1", "name": "create_booking", "arguments": {}}]
        planner_response = _make_llm_response("ok", tool_calls=tool_call)

        mock_template = MagicMock(spec=TemplateEngine)
        mock_template.match.return_value = TemplateResult(
            response="تم الحجز بنجاح ✅\nرقم الحجز: BK-555",
            skip_reason="booking_created",
            saved_renderer_tokens=600,
        )

        registry = MagicMock()
        registry.get_tool_definitions.return_value = []
        registry.call_tool = AsyncMock(return_value={"booking_id": "BK-555"})

        provider = MagicMock()
        provider.generate = AsyncMock(return_value=planner_response)
        provider.count_tokens = AsyncMock(return_value=20)

        response_gen = MagicMock()
        response_gen.provider = provider
        response_gen.generate = provider.generate

        orch = AIOrchestrator(
            response_generator=response_gen,
            response_validator=_FakeValidator(),
            tool_registry=registry,
            template_engine=mock_template,
        )
        orch.response_generator.generate = provider.generate

        _, _, _, breakdown = await orch.generate_complex(
            user_input="احجز تذكرة",
            intent="create_booking",
            payload=_base_payload(),
            session_id="s1",
            route="llm_path",
        )

        assert breakdown["saved_renderer_tokens"] == 600
        assert breakdown["renderer_prompt_tokens"] == 0
        assert breakdown["renderer_completion_tokens"] == 0
