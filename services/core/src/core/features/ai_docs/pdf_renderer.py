"""Branded report-pack PDF renderer (FIN-AI-004 A6).

Renders P&L / balance-sheet snapshots (``snapshot_data`` passed at generation
time) to a single A4 document via ReportLab. When the artifact is a DRAFT,
a diagonal translucent "DRAFT" overlay is drawn across the page so a
watermarked PDF can never be mistaken for an approved one; approval clears
``watermarked`` and regenerates a clean copy at the next download.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _num(value: Any) -> float:
    return float(value or 0)


def _fmt(value: Any) -> str:
    return f"{_num(value):,.2f}"


def _cash_row(label: str, amount: Any) -> list:
    return [Paragraph(label, _label_style()), Paragraph(_fmt(amount), _amount_style())]


def _label_style() -> ParagraphStyle:
    return ParagraphStyle(
        "pack-label",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#666666"),
    )


def _amount_style() -> ParagraphStyle:
    return ParagraphStyle(
        "pack-amount",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=10,
        alignment=TA_RIGHT,
    )


class _WatermarkCanvas(canvas.Canvas):
    """Draws a translucent diagonal DRAFT overlay on every page."""

    def __init__(self, *args: Any, watermarked: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._watermarked = watermarked

    def showPage(self) -> None:  # noqa: N802 (reportlab API name)
        if self._watermarked:
            self.saveState()
            self.translate(self._pagesize[0] / 2, self._pagesize[1] / 2)
            self.setFont("Helvetica-Bold", 64)
            self.setFillColor(colors.HexColor("#b91c1c"))
            self.setFillAlpha(0.10)
            self.rotate(45)
            self.drawCentredString(0, 0, "DRAFT")
            self.restoreState()
        super().showPage()


def _render_table(story: list[Any], doc: SimpleDocTemplate, rows: list[list[Any]]) -> None:
    table = Table(rows, colWidths=[doc.width * 0.6, doc.width * 0.4])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#cccccc")),
                ("GRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#e8e8e8")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    story.append(table)


def render_report_pdf(
    *,
    doc_type: str,
    snapshot_data: dict[str, Any],
    watermarked: bool,
    revision: str = "",
) -> bytes:
    """Render one report pack; ``doc_type`` is ``pnl`` or ``balance_sheet``."""
    title = "Profit &amp; Loss" if doc_type == "pnl" else "Balance Sheet"
    header = ParagraphStyle(
        "pack-title",
        parent=getSampleStyleSheet()["Heading1"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
    )
    sub = ParagraphStyle(
        "pack-sub",
        parent=getSampleStyleSheet()["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6 * mm,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    story: list[Any] = []
    story.append(Paragraph(title, header))
    subtitle = " ".join(
        [
            str(snapshot_data.get("period") or snapshot_data.get("as_of") or ""),
            f"(rev {revision})" if revision else "",
        ]
    ).strip()
    if subtitle:
        story.append(Paragraph(subtitle, sub))

    if doc_type == "pnl":
        rows = [["Account", "Amount"]]
        rows += [
            _cash_row(f"{r.get('code')} - {r.get('name')}", r.get("amount"))
            for r in snapshot_data.get("revenue", [])
        ]
        rows.append(["Total Revenue", snapshot_data.get("total_revenue")])
        rows.append([Paragraph("Expenses", _label_style()), Paragraph("", _amount_style())])
        rows += [
            _cash_row(f"{r.get('code')} - {r.get('name')}", r.get("amount"))
            for r in snapshot_data.get("expenses", [])
        ]
        rows.append(["Total Expenses", snapshot_data.get("total_expenses")])
        rows.append(["Net Income", snapshot_data.get("net_income")])
    else:
        rows = [["Account", "Balance"]]
        rows += [
            _cash_row(f"{r.get('code')} - {r.get('name')}", r.get("balance"))
            for r in snapshot_data.get("assets", [])
        ]
        rows.append(["Total Assets", snapshot_data.get("total_assets")])
        rows.append([Paragraph("Liabilities", _label_style()), Paragraph("", _amount_style())])
        rows += [
            _cash_row(f"{r.get('code')} - {r.get('name')}", r.get("balance"))
            for r in snapshot_data.get("liabilities", [])
        ]
        rows.append(["Total Liabilities", snapshot_data.get("total_liabilities")])
        rows.append([Paragraph("Equity", _label_style()), Paragraph("", _amount_style())])
        rows += [
            _cash_row(f"{r.get('code')} - {r.get('name')}", r.get("balance"))
            for r in snapshot_data.get("equity", [])
        ]
        rows.append(["Total Equity", snapshot_data.get("total_equity")])

    _render_table(story, doc, rows)
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            "Generated by Skyrict AI Docs. Figures are from the referenced approved "
            "financial snapshot and may not include closed-period adjustments."
            if watermarked
            else "Approved financial document - Skyrict AI Docs.",
            ParagraphStyle(
                "pack-footer",
                parent=getSampleStyleSheet()["Normal"],
                alignment=TA_CENTER,
                fontSize=8,
                textColor=colors.HexColor("#999999"),
            ),
        )
    )
    doc.build(story, canvasmaker=lambda *a, **k: _WatermarkCanvas(*a, **k, watermarked=watermarked))
    return buf.getvalue()
