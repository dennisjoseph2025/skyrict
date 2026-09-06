"""Unit tests for report CSV serialization helpers (RPT-BE-001) - no database."""

from __future__ import annotations

from decimal import Decimal

from core.features.reporting.runner import csv_buffer, json_safe_value


class TestCsvBuffer:
    def test_writes_header_and_coerced_rows(self) -> None:
        columns = ["bucket", "total"]
        rows = [{"bucket": "current", "total": Decimal("150.50")}]

        output = csv_buffer(columns=columns, rows=rows)

        assert output == "bucket,total\r\ncurrent,150.50\r\n"

    def test_quotes_commas_and_newlines(self) -> None:
        columns = ["name", "note"]
        rows = [{"name": "A, B", "note": "line1\nline2"}]

        output = csv_buffer(columns=columns, rows=rows)

        # csv module escapes embedded commas/newlines with quotes.
        assert '"A, B"' in output
        assert "line1\nline2" in output

    def test_missing_columns_rendered_empty(self) -> None:
        columns = ["a", "b", "c"]
        rows = [{"a": 1}]

        output = csv_buffer(columns=columns, rows=rows)

        assert output == "a,b,c\r\n1,,\r\n"

    def test_ignores_extra_keys_in_rows(self) -> None:
        columns = ["a"]
        rows = [{"a": 1, "secret_column": "nope"}]

        output = csv_buffer(columns=columns, rows=rows)

        assert "secret_column" not in output
        assert output == "a\r\n1\r\n"

    def test_escapes_formula_sigils_but_keeps_negatives(self) -> None:
        columns = ["name", "delta"]
        rows = [
            {"name": '=HYPERLINK("http://evil")', "delta": -2.3},
            {"name": "+1", "delta": 0},
            {"name": "@cmd", "delta": 0},
            {"name": "\tcmd", "delta": 0},
            {"name": "plain", "delta": -10},
        ]

        output = csv_buffer(columns=columns, rows=rows)

        lines = output.strip().splitlines()
        assert "'=HYPERLINK(" in lines[1]  # escaped inside the QUOTE_MINIMAL field
        assert "'+1" in lines[2]
        assert "'@cmd" in lines[3]
        assert "'\tcmd" in lines[4]
        assert "plain,-10" in lines[5]
        assert "-2.3" in lines[1]  # negatives pass through untouched


class TestJsonSafeValue:
    def test_decimal_becomes_string(self) -> None:
        assert json_safe_value(Decimal("123.4567")) == "123.4567"

    def test_none_passthrough(self) -> None:
        assert json_safe_value(None) is None

    def test_bool_and_int_passthrough(self) -> None:
        assert json_safe_value(True) is True
        assert json_safe_value(42) == 42

    def test_string_passthrough(self) -> None:
        assert json_safe_value("hello") == "hello"
