from __future__ import annotations

import copy
import csv
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from cli.models import AnalystType, AssetType
from cli.utils import (
    detect_asset_type,
    filter_analysts_for_asset_type,
    normalize_ticker_symbol,
)
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env


DEFAULT_TICKER_COLUMN = "ticker"
DEFAULT_TICKER_COLUMN_ALIASES = ("ticker", "symbol", "ticker_symbol")
DEFAULT_BATCH_ANALYSTS = [
    AnalystType.MARKET,
    AnalystType.SOCIAL,
    AnalystType.NEWS,
    AnalystType.FUNDAMENTALS,
]
ANALYST_ALIASES = {
    "market": AnalystType.MARKET,
    "social": AnalystType.SOCIAL,
    "sentiment": AnalystType.SOCIAL,
    "news": AnalystType.NEWS,
    "fundamentals": AnalystType.FUNDAMENTALS,
    "fundamental": AnalystType.FUNDAMENTALS,
}


@dataclass(frozen=True)
class BatchRunResult:
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    decision: str = ""
    report_path: Path | None = None
    error: str = ""


def load_tickers_from_csv(
    csv_path: Path,
    ticker_column: str = DEFAULT_TICKER_COLUMN,
) -> list[str]:
    """Load normalized ticker symbols from a CSV file.

    Headered CSVs should include a ticker-like column. For simple one-column
    files without a header, the first column is read as the ticker list.
    Duplicate tickers are ignored after their first occurrence.
    """
    csv_path = Path(csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError(f"{csv_path} does not contain any ticker rows.")

    column_name = ticker_column.strip().lower()
    header = [cell.strip().lower() for cell in rows[0]]
    header_index = _find_ticker_header_index(header, column_name)

    if header_index is None and column_name != DEFAULT_TICKER_COLUMN:
        raise ValueError(
            f"{csv_path} does not contain a '{ticker_column}' column."
        )

    ticker_index = header_index if header_index is not None else 0
    data_rows = rows[1:] if header_index is not None else rows

    tickers: list[str] = []
    seen: set[str] = set()
    start_row = 2 if header_index is not None else 1
    for row_number, row in enumerate(data_rows, start=start_row):
        if ticker_index >= len(row):
            continue

        raw_ticker = row[ticker_index].strip()
        if not raw_ticker:
            continue

        ticker = normalize_ticker_symbol(raw_ticker)
        _validate_batch_ticker(ticker, row_number)
        if ticker in seen:
            continue

        seen.add(ticker)
        tickers.append(ticker)

    if not tickers:
        raise ValueError(f"{csv_path} does not contain any valid ticker symbols.")

    return tickers


def _find_ticker_header_index(header: Sequence[str], column_name: str) -> int | None:
    if column_name in header:
        return header.index(column_name)

    if column_name == DEFAULT_TICKER_COLUMN:
        for alias in DEFAULT_TICKER_COLUMN_ALIASES:
            if alias in header:
                return header.index(alias)

    return None


def _validate_batch_ticker(ticker: str, row_number: int) -> None:
    if len(ticker) > 32:
        raise ValueError(
            f"Ticker on CSV row {row_number} is longer than 32 characters."
        )
    if not all(ch.isalnum() or ch in "._-^" for ch in ticker):
        raise ValueError(
            f"Ticker {ticker!r} on CSV row {row_number} contains unsupported characters."
        )


def resolve_analysis_date(analysis_date: str | None) -> str:
    if analysis_date is None:
        return datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        parsed = datetime.datetime.strptime(analysis_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Analysis date must use YYYY-MM-DD format.") from exc

    if parsed > datetime.datetime.now().date():
        raise ValueError("Analysis date cannot be in the future.")

    return analysis_date


def parse_analyst_keys(raw_analysts: str | None) -> list[AnalystType] | None:
    if raw_analysts is None or not raw_analysts.strip():
        return None

    analysts: list[AnalystType] = []
    for raw_key in raw_analysts.split(","):
        key = raw_key.strip().lower()
        if not key:
            continue
        analyst = ANALYST_ALIASES.get(key)
        if analyst is None:
            valid = ", ".join(sorted(ANALYST_ALIASES))
            raise ValueError(f"Unknown analyst '{raw_key}'. Valid values: {valid}.")
        if analyst not in analysts:
            analysts.append(analyst)

    if not analysts:
        raise ValueError("At least one analyst must be selected.")

    return analysts


def resolve_analyst_keys(
    asset_type: AssetType,
    requested_analysts: Sequence[AnalystType] | None = None,
) -> list[str]:
    analysts = list(requested_analysts or DEFAULT_BATCH_ANALYSTS)
    analysts = filter_analysts_for_asset_type(analysts, asset_type)
    if not analysts:
        raise ValueError(f"No analysts are available for asset type {asset_type.value}.")
    return [analyst.value for analyst in analysts]


def build_batch_config(
    *,
    checkpoint: bool,
    research_depth: int | None = None,
    llm_provider: str | None = None,
    shallow_thinker: str | None = None,
    deep_thinker: str | None = None,
    backend_url: str | None = None,
    output_language: str | None = None,
    google_thinking_level: str | None = None,
    openai_reasoning_effort: str | None = None,
    anthropic_effort: str | None = None,
) -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    if research_depth is not None:
        if research_depth < 1:
            raise ValueError("Research depth must be at least 1.")
        config["max_debate_rounds"] = research_depth
        config["max_risk_discuss_rounds"] = research_depth
    if llm_provider is not None:
        config["llm_provider"] = llm_provider.lower()
    if shallow_thinker is not None:
        config["quick_think_llm"] = shallow_thinker
    if deep_thinker is not None:
        config["deep_think_llm"] = deep_thinker
    if backend_url is not None:
        config["backend_url"] = backend_url
    if output_language is not None:
        config["output_language"] = output_language
    if google_thinking_level is not None:
        config["google_thinking_level"] = google_thinking_level
    if openai_reasoning_effort is not None:
        config["openai_reasoning_effort"] = openai_reasoning_effort
    if anthropic_effort is not None:
        config["anthropic_effort"] = anthropic_effort

    config["checkpoint_enabled"] = checkpoint
    return config


def ensure_batch_api_key(provider: str) -> None:
    env_var = get_api_key_env(provider)
    if env_var is None:
        return
    if not os.environ.get(env_var):
        raise RuntimeError(
            f"{env_var} is not set. Set it in your environment or .env before "
            "running non-interactive batch analysis."
        )


def run_batch_analysis(
    *,
    tickers: Sequence[str],
    analysis_date: str,
    config: dict,
    requested_analysts: Sequence[AnalystType] | None,
    output_dir: Path,
    save_report: Callable[[dict, str, Path], Path],
    continue_on_error: bool = True,
    on_start: Callable[[int, int, str, AssetType, Sequence[str]], None] | None = None,
    on_success: Callable[[BatchRunResult], None] | None = None,
    on_error: Callable[[BatchRunResult], None] | None = None,
) -> list[BatchRunResult]:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    results: list[BatchRunResult] = []
    total = len(tickers)
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, ticker in enumerate(tickers, start=1):
        asset_type = detect_asset_type(ticker)
        selected_analysts = resolve_analyst_keys(asset_type, requested_analysts)

        if on_start is not None:
            on_start(index, total, ticker, asset_type, selected_analysts)

        try:
            graph = TradingAgentsGraph(
                selected_analysts,
                config=copy.deepcopy(config),
                debug=False,
            )
            final_state, decision = graph.propagate(
                ticker,
                analysis_date,
                asset_type=asset_type.value,
            )
            report_dir = output_dir / safe_ticker_component(ticker) / analysis_date
            report_path = save_report(final_state, ticker, report_dir)
            result = BatchRunResult(
                ticker=ticker,
                analysis_date=analysis_date,
                asset_type=asset_type.value,
                status="success",
                decision=decision,
                report_path=report_path,
            )
            if on_success is not None:
                on_success(result)
        except Exception as exc:
            result = BatchRunResult(
                ticker=ticker,
                analysis_date=analysis_date,
                asset_type=asset_type.value,
                status="error",
                error=str(exc),
            )
            if on_error is not None:
                on_error(result)
            if not continue_on_error:
                results.append(result)
                break

        results.append(result)

    return results


def write_batch_summary(output_dir: Path, results: Iterable[BatchRunResult]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "batch_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "analysis_date",
                "asset_type",
                "status",
                "decision",
                "report_path",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "ticker": result.ticker,
                    "analysis_date": result.analysis_date,
                    "asset_type": result.asset_type,
                    "status": result.status,
                    "decision": result.decision,
                    "report_path": str(result.report_path or ""),
                    "error": result.error,
                }
            )

    return summary_path
