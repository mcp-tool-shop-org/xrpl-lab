"""Tests for structured payload parsing (Phase 2B)."""

from xrpl_lab.modules import _parse_action_args


class TestParseActionArgs:
    """Tests for the quote-aware payload parser."""

    def test_simple_key_value(self):
        result = _parse_action_args("currency=LAB amount=100")
        assert result == {"currency": "LAB", "amount": "100"}

    def test_double_quoted_value(self):
        result = _parse_action_args('memo="hello world"')
        assert result == {"memo": "hello world"}

    def test_single_quoted_value(self):
        result = _parse_action_args("memo='hello world'")
        assert result == {"memo": "hello world"}

    def test_mixed_quoted_and_plain(self):
        result = _parse_action_args('currency=LAB memo="my memo text" amount=100')
        assert result == {"currency": "LAB", "memo": "my memo text", "amount": "100"}

    def test_empty_string(self):
        result = _parse_action_args("")
        assert result == {}

    def test_none_input(self):
        result = _parse_action_args(None)
        assert result == {}

    def test_quoted_with_equals(self):
        result = _parse_action_args('memo="a=b"')
        assert result == {"memo": "a=b"}

    def test_spaces_around_values(self):
        result = _parse_action_args("  currency=LAB   amount=10  ")
        assert result == {"currency": "LAB", "amount": "10"}

    def test_empty_value(self):
        result = _parse_action_args("currency=")
        assert result == {"currency": ""}

    def test_numeric_string(self):
        result = _parse_action_args("amount=3.14 count=42")
        assert result == {"amount": "3.14", "count": "42"}

    def test_boolean_string(self):
        result = _parse_action_args("flag=true")
        assert result == {"flag": "true"}
