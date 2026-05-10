"""HtmlReporter — generates a self-contained HTML report with a matplotlib gauge
chart embedded as a base64 PNG.  Saves the file to data/raw/reports/ and
registers the path in the relatorios table via Repository.
"""
from __future__ import annotations

import base64
import io
import math
import subprocess
import webbrowser
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from jinja2 import Environment, FileSystemLoader
from loguru import logger

if TYPE_CHECKING:
    from src.processors.fundamentals import ScoreResult
    from src.storage.sql.repository import Repository

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "reports"


# ---------------------------------------------------------------------------
# Gauge chart
# ---------------------------------------------------------------------------

def _make_gauge(score: float) -> str:
    """Return a base64-encoded PNG of a half-circle gauge for *score* (0–100)."""

    fig, ax = plt.subplots(figsize=(5, 2.8))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#0f1117")

    # Arc segments: red 0-33, yellow 33-66, green 66-100
    segments = [
        (0,   33,  "#fc8181"),
        (33,  66,  "#ecc94b"),
        (66,  100, "#68d391"),
    ]
    for lo, hi, color in segments:
        theta1 = 180.0 - lo * 1.8   # map 0→180°, 100→0°
        theta2 = 180.0 - hi * 1.8
        arc = mpatches.Wedge(
            center=(0.5, 0.0),
            r=0.42,
            theta1=theta2,
            theta2=theta1,
            width=0.12,
            color=color,
            alpha=0.85,
        )
        ax.add_patch(arc)

    # Needle
    angle_deg = 180.0 - score * 1.8
    angle_rad = math.radians(angle_deg)
    needle_len = 0.34
    nx = 0.5 + needle_len * math.cos(angle_rad)
    ny = 0.0 + needle_len * math.sin(angle_rad)
    ax.annotate(
        "",
        xy=(nx, ny),
        xytext=(0.5, 0.0),
        arrowprops=dict(arrowstyle="-|>", color="white", lw=2.5),
    )

    # Center hub
    hub = plt.Circle((0.5, 0.0), 0.04, color="#e2e8f0", zorder=5)
    ax.add_patch(hub)

    # Score label
    color_label = "#68d391" if score >= 66 else ("#ecc94b" if score >= 33 else "#fc8181")
    ax.text(
        0.5, 0.22, f"{score:.1f}",
        ha="center", va="center",
        fontsize=22, fontweight="bold",
        color=color_label,
        transform=ax.transAxes,
    )
    ax.text(
        0.5, 0.10, "/ 100",
        ha="center", va="center",
        fontsize=10, color="#718096",
        transform=ax.transAxes,
    )

    # Ticks 0, 50, 100
    for val, label in ((0, "0"), (50, "50"), (100, "100")):
        a = math.radians(180.0 - val * 1.8)
        r = 0.47
        ax.text(
            0.5 + r * math.cos(a),
            r * math.sin(a) - 0.05,
            label,
            ha="center", va="center",
            fontsize=7, color="#718096",
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.1, 0.55)
    ax.axis("off")
    plt.tight_layout(pad=0.1)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class HtmlReporter:
    def __init__(self, repo: "Repository") -> None:
        self._repo = repo
        self._jinja = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        result: "ScoreResult",
        snapshot: dict,
        open_browser: bool = False,
    ) -> Path:
        """Build the HTML report, save it, register in DB, and optionally open it."""
        ticker = result.ticker
        today = date.today().isoformat()
        filename = f"{ticker}_{today}.html"
        out_path = _REPORTS_DIR / filename

        gauge_b64 = _make_gauge(result.score_geral)

        # Map snapshot keys to template-friendly fund dict
        fund = {
            "roe": snapshot.get("roe"),
            "roic": snapshot.get("roic"),
            "margem_liquida": snapshot.get("margem_liquida"),
            "divida_liquida_ebitda": snapshot.get("divida_liquida_ebitda"),
            "liquidez_corrente": snapshot.get("liquidez_corrente"),
            "pl": snapshot.get("pl"),
            "pvp": snapshot.get("pvp"),
            "dy": snapshot.get("dy"),
            "cagr_receita_5a": snapshot.get("cagr_receita_5a"),
            "payout": snapshot.get("payout"),
        }

        tmpl = self._jinja.get_template("report_template.html")
        html = tmpl.render(
            ticker=ticker,
            data_coleta=today,
            gauge_b64=gauge_b64,
            score_geral=result.score_geral,
            score_qualidade=result.score_qualidade,
            score_valuation=result.score_valuation,
            score_momento=result.score_momento,
            fund=fund,
            momento=result.momento_detail,
            veredito=result.veredito,
            alertas=result.alertas,
        )

        out_path.write_text(html, encoding="utf-8")
        logger.info(f"HtmlReporter | relatório salvo | path={out_path}")

        # Register in DB (best-effort)
        try:
            self._repo.insert_relatorio(ticker, str(out_path), result.score_geral)
        except Exception as exc:
            logger.warning(f"HtmlReporter | insert_relatorio falhou (não crítico) | erro={exc}")

        if open_browser:
            _open(out_path)

        return out_path


def _open(path: Path) -> None:
    """Open *path* in the default browser cross-platform."""
    try:
        webbrowser.open(path.as_uri())
    except Exception as exc:
        logger.warning(f"webbrowser.open falhou: {exc}")
