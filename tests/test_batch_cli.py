import csv
import unittest

from cli.batch import (
    build_batch_config,
    load_tickers_from_csv,
    parse_analyst_keys,
    resolve_analyst_keys,
    write_batch_summary,
    BatchRunResult,
)
from cli.models import AnalystType, AssetType


class BatchCliTests(unittest.TestCase):
    def test_load_tickers_from_headered_csv_deduplicates_and_normalizes(self):
        csv_path = self.tmp_path / "tickers.csv"
        csv_path.write_text(
            "ticker,name\n aapl ,Apple\nMSFT,Microsoft\naapl,Duplicate\n",
            encoding="utf-8",
        )

        self.assertEqual(load_tickers_from_csv(csv_path), ["AAPL", "MSFT"])

    def test_load_tickers_supports_headerless_single_column_csv(self):
        csv_path = self.tmp_path / "tickers.csv"
        csv_path.write_text("spy\n7203.t\nBRK.B\n", encoding="utf-8")

        self.assertEqual(load_tickers_from_csv(csv_path), ["SPY", "7203.T", "BRK.B"])

    def test_load_tickers_supports_symbol_alias_header(self):
        csv_path = self.tmp_path / "symbols.csv"
        csv_path.write_text("symbol\nbtc-usd\neth-usdt\n", encoding="utf-8")

        self.assertEqual(load_tickers_from_csv(csv_path), ["BTC-USD", "ETH-USDT"])

    def test_load_tickers_rejects_missing_custom_column(self):
        csv_path = self.tmp_path / "symbols.csv"
        csv_path.write_text("ticker\nAAPL\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "does not contain a 'symbol' column"):
            load_tickers_from_csv(csv_path, ticker_column="symbol")

    def test_parse_analyst_keys_accepts_sentiment_alias(self):
        self.assertEqual(
            parse_analyst_keys("market,sentiment,news"),
            [AnalystType.MARKET, AnalystType.SOCIAL, AnalystType.NEWS],
        )

    def test_resolve_analyst_keys_filters_fundamentals_for_crypto(self):
        analysts = resolve_analyst_keys(AssetType.CRYPTO, requested_analysts=None)

        self.assertEqual(analysts, ["market", "social", "news"])

    def test_build_batch_config_overrides_expected_fields(self):
        config = build_batch_config(
            checkpoint=True,
            research_depth=2,
            llm_provider="openrouter",
            shallow_thinker="quick-model",
            deep_thinker="deep-model",
            output_language="Spanish",
        )

        self.assertTrue(config["checkpoint_enabled"])
        self.assertEqual(config["max_debate_rounds"], 2)
        self.assertEqual(config["max_risk_discuss_rounds"], 2)
        self.assertEqual(config["llm_provider"], "openrouter")
        self.assertEqual(config["quick_think_llm"], "quick-model")
        self.assertEqual(config["deep_think_llm"], "deep-model")
        self.assertEqual(config["output_language"], "Spanish")

    def test_write_batch_summary(self):
        result = BatchRunResult(
            ticker="AAPL",
            analysis_date="2026-01-10",
            asset_type="stock",
            status="success",
            decision="Buy",
            report_path=self.tmp_path / "AAPL" / "complete_report.md",
        )

        summary_path = write_batch_summary(self.tmp_path, [result])

        with summary_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(rows[0]["ticker"], "AAPL")
        self.assertEqual(rows[0]["status"], "success")
        self.assertEqual(rows[0]["decision"], "Buy")

    def setUp(self):
        from tempfile import TemporaryDirectory

        self._tmpdir = TemporaryDirectory()
        from pathlib import Path

        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()
