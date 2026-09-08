"""Unit tests for SKY-67 C2 FX: invoice currencies, rates, and the guardrail.

The service must never silently invent an FX rate: any invoice in a currency
other than the tenant default needs a rate on file for the invoice date, else
creation is rejected with a ``ValidationError``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pytest import mark

from core.core.config import settings
from core.domain.entities import ExchangeRate, Invoice
from core.features.finance.ports import SalesOrderForInvoicing, SalesOrderLine
from core.features.finance.service import FinanceService, InvoiceLineInput
from skyrict_common.exceptions import ValidationError

pytestmark = mark.unit


class FakeAccount:
    def __init__(self, code: str) -> None:
        self.id = uuid.uuid4()
        self.code = code
        self.is_active = True


class StubRepo:
    def __init__(self) -> None:
        self.accounts: dict[str, FakeAccount] = {}
        self.rates: dict[tuple[str, str], ExchangeRate] = {}
        self.created: list[Invoice] = []
        self.next_number = 1

    async def get_account_by_code(self, code, tenant_id):
        return self.accounts.setdefault(code, FakeAccount(code))

    async def next_invoice_number(self, tenant_id, year):
        number = f"INV-{year}-{self.next_number:05d}"
        self.next_number += 1
        return number

    async def create_invoice(self, invoice: Invoice) -> Invoice:
        if invoice.id is None:
            invoice = Invoice(
                tenant_id=invoice.tenant_id,
                invoice_number=invoice.invoice_number,
                customer_id=invoice.customer_id,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                status=invoice.status,
                total=invoice.total,
                currency=invoice.currency,
                exchange_rate=invoice.exchange_rate,
                source=invoice.source,
                source_ref=invoice.source_ref,
                lines=invoice.lines,
                id=uuid.uuid4(),
            )
        self.created.append(invoice)
        return invoice

    async def get_invoice_by_source_ref(self, source, source_ref, tenant_id):
        return None

    async def get_exchange_rate(self, tenant_id, base_currency, quote_currency, on_date):
        return self.rates.get((base_currency, quote_currency))

    async def upsert_exchange_rate(self, rate: ExchangeRate) -> ExchangeRate:
        self.rates[(rate.base_currency, rate.quote_currency)] = rate
        return rate

    async def list_exchange_rates(self, tenant_id, *, currency=None):
        return list(self.rates.values())


class RecordingSinks:
    def __init__(self) -> None:
        self.audit: list[dict] = []
        self.events: list[tuple[str, str, uuid.UUID, str]] = []

    async def log(self, *, tenant_id, user_id, action, target, details, **kwargs):
        self.audit.append(
            {"tenant_id": tenant_id, "action": action, "target": target, "details": details}
        )

    def invoice_created(self, *, invoice_id, invoice_number, tenant_id, correlation_id):
        self.events.append((invoice_number, str(invoice_id), tenant_id, correlation_id))


class DefaultCurrency:
    def __init__(self, code: str | None) -> None:
        self._code = code

    async def get_default_currency(self, tenant_id) -> str | None:
        return self._code


def _make_service(repo: StubRepo, default_code: str | None = "USD") -> FinanceService:
    return FinanceService(
        repo=repo,
        audit=RecordingSinks(),
        events=RecordingSinks(),
        default_currency=DefaultCurrency(default_code),
    )


def _lines() -> list[InvoiceLineInput]:
    return [
        InvoiceLineInput(
            description="Consulting",
            account_code="REV-1000",
            quantity=Decimal("2"),
            unit_price=Decimal("50.00"),
        )
    ]


async def test_default_currency_falls_back_to_platform_default() -> None:
    svc = _make_service(StubRepo(), default_code=None)
    assert await svc.default_currency(uuid.uuid4()) == settings.DEFAULT_CURRENCY


async def test_manual_invoice_default_currency_uses_identity_rate() -> None:
    repo = StubRepo()
    svc = _make_service(repo, default_code="USD")
    invoice = await svc.create_manual_invoice(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 6, 15),
        lines=_lines(),
    )
    assert invoice.currency == "USD"
    assert invoice.exchange_rate == Decimal("1")


async def test_manual_invoice_in_foreign_currency_uses_on_file_rate() -> None:
    tenant_id = uuid.uuid4()
    repo = StubRepo()
    repo.rates[("USD", "INR")] = ExchangeRate(
        tenant_id=tenant_id,
        base_currency="USD",
        quote_currency="INR",
        effective_date=date(2026, 1, 1),
        rate=Decimal("83.000000"),
    )
    svc = _make_service(repo, default_code="USD")

    invoice = await svc.create_manual_invoice(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 6, 15),
        currency="inr",
        lines=_lines(),
    )

    assert invoice.currency == "INR"
    assert invoice.exchange_rate == Decimal("83.000000")


async def test_manual_invoice_unknown_rate_raises_guardrail() -> None:
    repo = StubRepo()
    svc = _make_service(repo, default_code="USD")
    with pytest.raises(ValidationError, match="No exchange rate"):
        await svc.create_manual_invoice(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            invoice_date=date(2026, 6, 1),
            due_date=date(2026, 6, 15),
            currency="EUR",
            lines=_lines(),
        )
    assert repo.created == []


async def test_manual_invoice_unsupported_currency_rejected() -> None:
    svc = _make_service(StubRepo(), default_code="USD")
    with pytest.raises(ValidationError, match="Unsupported currency"):
        await svc.create_manual_invoice(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            invoice_date=date(2026, 6, 1),
            due_date=date(2026, 6, 15),
            currency="XYZ",
            lines=_lines(),
        )


async def test_set_exchange_rate_validates_and_quantizes() -> None:
    repo = StubRepo()
    svc = _make_service(repo, default_code="USD")
    rate = await svc.set_exchange_rate(
        uuid.uuid4(),
        base_currency="usd",
        quote_currency="eur",
        effective_date=date(2026, 6, 1),
        rate=Decimal("0.923456789"),
    )
    assert rate.rate == Decimal("0.923457")
    assert repo.rates[("USD", "EUR")] is rate


async def test_set_exchange_rate_rejects_same_currency_and_non_positive() -> None:
    svc = _make_service(StubRepo(), default_code="USD")
    with pytest.raises(ValidationError, match="must differ"):
        await svc.set_exchange_rate(
            uuid.uuid4(),
            base_currency="USD",
            quote_currency="USD",
            effective_date=date(2026, 6, 1),
            rate=Decimal("1"),
        )
    with pytest.raises(ValidationError, match="positive"):
        await svc.set_exchange_rate(
            uuid.uuid4(),
            base_currency="USD",
            quote_currency="EUR",
            effective_date=date(2026, 6, 1),
            rate=Decimal("0"),
        )


async def test_exchange_rate_to_default_returns_identity_for_default() -> None:
    svc = _make_service(StubRepo(), default_code="USD")
    rate = await svc.exchange_rate_to_default(
        uuid.uuid4(), quote_currency="usd", on_date=date(2026, 6, 1)
    )
    assert rate.rate == Decimal("1")
    assert rate.quote_currency == "USD"


async def test_exchange_rate_to_default_returns_on_file_rate() -> None:
    tenant_id = uuid.uuid4()
    repo = StubRepo()
    stored = ExchangeRate(
        tenant_id=tenant_id,
        base_currency="USD",
        quote_currency="INR",
        effective_date=date(2026, 1, 1),
        rate=Decimal("83"),
    )
    repo.rates[("USD", "INR")] = stored
    svc = _make_service(repo, default_code="USD")

    rate = await svc.exchange_rate_to_default(
        tenant_id, quote_currency="INR", on_date=date(2026, 6, 1)
    )

    assert rate is stored


async def test_create_from_order_uses_order_currency_and_rate() -> None:
    tenant_id = uuid.uuid4()
    repo = StubRepo()
    repo.rates[("USD", "EUR")] = ExchangeRate(
        tenant_id=tenant_id,
        base_currency="USD",
        quote_currency="EUR",
        effective_date=date(2026, 1, 1),
        rate=Decimal("0.9"),
    )
    svc = _make_service(repo, default_code="USD")

    order = SalesOrderForInvoicing(
        tenant_id=tenant_id,
        order_id=str(uuid.uuid4()),
        customer_id=uuid.uuid4(),
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 6, 15),
        lines=(
            SalesOrderLine(
                description="Widgets",
                account_id=None,
                quantity=Decimal("3"),
                unit_price=Decimal("10"),
            ),
        ),
        currency="EUR",
    )
    invoice = await svc.create_from_order(order)
    assert invoice.currency == "EUR"
    assert invoice.exchange_rate == Decimal("0.900000")
