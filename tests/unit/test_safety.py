import pytest

from app.ai.safety import InputSafetyGuard, ResponseValidator
from app.core.exceptions import ValidationException


def test_input_safety_rejects_blank_messages():
    guard = InputSafetyGuard()
    with pytest.raises(ValidationException):
        guard.validate_user_message("   ")


def test_response_validator_trims_content():
    validator = ResponseValidator()
    assert validator.validate_response("  hello  ") == "hello"
