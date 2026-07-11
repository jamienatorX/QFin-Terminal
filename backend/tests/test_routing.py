import unittest
from unittest.mock import AsyncMock, patch

import main
import financial_data_warehouse
import qwen_client


class AgentRoutingTests(unittest.TestCase):
    def setUp(self):
        self.supabase_patch = patch("main.supabase_is_configured", return_value=False)
        self.yahoo_patch = patch("main.yahoo_symbol_search", return_value=None)
        self.supabase_patch.start()
        self.yahoo_patch.start()

    def tearDown(self):
        self.yahoo_patch.stop()
        self.supabase_patch.stop()

    def assert_route(self, prompt, expected_kind):
        route = main.classify_message(prompt)
        self.assertEqual(route["kind"], expected_kind, route)
        return route

    def test_identity_prompt_is_local_casual_reply(self):
        self.assert_route("Hello, who are you and what can you help me with?", "casual")

    def test_general_questions_do_not_become_tickers(self):
        prompts = [
            "Explain photosynthesis to a 12-year-old.",
            "What is AI and how does it work?",
            "What does NASA do?",
            "Write a polite email asking for a meeting.",
            "How do I boil an egg?",
            "Explain gravity simply.",
            "Translate good morning into Indonesian.",
            "Give me three study tips.",
            "What is the capital of Japan?",
            "Why is the sky blue?",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assert_route(prompt, "general")

    def test_finance_acronyms_are_concepts_not_tickers(self):
        prompts = [
            "Explain WACC, its formula, and when it is used.",
            "How does a DCF valuation work?",
            "What is ROE and how should I interpret it?",
            "Build an emergency fund plan for $2,000 monthly spending.",
            "How does inflation affect bond prices?",
            "Explain duration and convexity.",
            "What is an options hedge?",
            "How should I allocate a retirement portfolio?",
            "Explain capital gains tax at a high level.",
            "What is working capital and why does it matter?",
            "How do interest rates affect a mortgage?",
            "What is the difference between an ETF and a mutual fund?",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assert_route(prompt, "finance_concept")

    def test_known_and_explicit_tickers_route_to_company(self):
        self.assertEqual(self.assert_route("Analyze AAPL", "company")["ticker"], "AAPL")
        self.assertEqual(self.assert_route("Analyze SNOW stock", "company")["ticker"], "SNOW")

    def test_indonesian_company_request_preserves_deep_intent(self):
        route = self.assert_route("Analisis BBCA secara lengkap", "company")
        self.assertEqual(route["ticker"], "BBCA.JK")
        self.assertEqual(route["detail"], "deep")

    def test_compare_supports_and_as_well_as_vs(self):
        route = self.assert_route("Compare AAPL and NVDA on valuation", "comparison")
        self.assertEqual(route["tickers"], ["AAPL", "NVDA"])

        aliases = self.assert_route("Compare Apple vs Microsoft", "comparison")
        self.assertEqual(aliases["tickers"], ["AAPL", "MSFT"])

        bare = self.assert_route("AAPL vs NVDA", "comparison")
        self.assertEqual(bare["tickers"], ["AAPL", "NVDA"])

        with_separator = self.assert_route("Compare Tesla with Apple", "comparison")
        self.assertEqual(with_separator["tickers"], ["TSLA", "AAPL"])

        choice = self.assert_route("Which stock is better, Tesla or Apple?", "comparison")
        self.assertEqual(choice["tickers"], ["TSLA", "AAPL"])

    def test_blank_input_becomes_fast_greeting(self):
        payload = main.AgentChatRequest(message="   ")
        self.assertEqual(main.extract_chat_query(payload), "Hello")

    def test_exchange_suffix_is_required_for_warehouse_identity(self):
        self.assertTrue(main.warehouse_row_matches_symbol({"provider_symbol": "BBCA.JK"}, "BBCA.JK"))
        self.assertFalse(main.warehouse_row_matches_symbol({"provider_symbol": "BBCA"}, "BBCA.JK"))
        self.assertEqual(financial_data_warehouse._symbol_candidates("BBCA.JK"), ["BBCA.JK"])

    def test_finance_fallback_omits_missing_metric_spam(self):
        answer = main.build_company_facts_fallback(
            "Analyze AAPL",
            {
                "ticker": "AAPL",
                "company_name": "Apple",
                "market_data": {"last_price": 200.0},
                "financial_metrics": {"gross_margin": "46.00%"},
                "source": "test",
            },
            "Model fallback used.",
        )
        self.assertIn("Last price: 200.0", answer)
        self.assertIn("Gross margin: 46.00%", answer)
        self.assertNotIn("Unavailable in supplied backend data", answer)

    def test_comparison_fallback_identifies_measured_leaders(self):
        facts = {
            "AAA": {
                "market_data": {"forward_pe": "20.00x"},
                "financial_metrics": {"revenue_growth": "10.00%", "operating_margin": "15.00%", "debt_to_equity": "40.00%"},
            },
            "BBB": {
                "market_data": {"forward_pe": "15.00x"},
                "financial_metrics": {"revenue_growth": "20.00%", "operating_margin": "25.00%", "debt_to_equity": "20.00%"},
            },
        }
        answer = main.build_comparison_facts_fallback(
            "Compare AAA and BBB",
            {"tickers": ["AAA", "BBB"]},
            facts,
            "fallback",
        )
        self.assertIn("Revenue growth: BBB leads", answer)
        self.assertIn("Forward P/E valuation: BBB leads", answer)
        self.assertIn("Balance-sheet leverage: BBB leads", answer)

    def test_deterministic_concept_fallback_covers_core_finance_topics(self):
        for prompt, expected in [
            ("Explain WACC", "blended required return"),
            ("How does a DCF work?", "forecasting future cash flows"),
            ("Explain bond duration", "price sensitivity"),
            ("Create an emergency fund", "three to six months"),
        ]:
            with self.subTest(prompt=prompt):
                self.assertIn(expected, main.build_finance_concept_fallback(prompt, "fallback"))


class FinanceEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_usable_warehouse_is_still_enriched_with_live_market_data(self):
        warehouse = {
            "symbol": "AAPL",
            "status": "available",
            "profile": {"provider_symbol": "AAPL", "company_name": "Apple", "currency": "USD"},
            "valuation": {"provider_symbol": "AAPL", "market_cap": 1_000_000},
            "bank_kpi": None,
            "statement_rows": [],
            "coverage_rows": [],
        }
        live = {
            "ticker": "AAPL",
            "company_name": "Apple",
            "currency": "USD",
            "market_data": {"last_price": 200.0, "forward_pe": "25.00x"},
            "financial_metrics": {"return_on_equity": "150.00%"},
            "historical_financials": {},
            "data_status": "available",
        }
        with (
            patch("main.load_warehouse_snapshot", return_value=warehouse),
            patch("main.fmp_is_configured", return_value=False),
            patch("main.fetch_financial_data_async", new=AsyncMock(return_value=live)) as fetch_live,
        ):
            result = await main.get_company_facts_async("AAPL")

        fetch_live.assert_awaited_once_with("AAPL")
        self.assertEqual(result["market_data"]["last_price"], 200.0)
        self.assertEqual(result["market_data"]["forward_pe"], "25.00x")
        self.assertEqual(result["financial_metrics"]["return_on_equity"], "150.00%")


class QwenModelRoutingTests(unittest.TestCase):
    def test_general_questions_use_flash_profile_first(self):
        messages = main.build_general_prompt("Explain photosynthesis simply.")
        self.assertEqual(qwen_client._detect_task_type(messages), "general")
        self.assertEqual(qwen_client._model_chain("general")[0], "qwen3.6-flash")

    def test_standard_company_analysis_uses_fast_profile(self):
        messages = main.build_finance_prompt(
            "Analyze AAPL",
            {"kind": "company", "ticker": "AAPL", "detail": "standard"},
            {"ticker": "AAPL"},
        )
        self.assertEqual(qwen_client._detect_task_type(messages), "fast")

    def test_explicit_deep_analysis_uses_deep_profile(self):
        messages = main.build_finance_prompt(
            "Give me a comprehensive analysis of AAPL",
            {"kind": "company", "ticker": "AAPL", "detail": "deep"},
            {"ticker": "AAPL"},
        )
        self.assertEqual(qwen_client._detect_task_type(messages), "deep")

    def test_standard_tasks_have_shorter_budgets_than_deep_analysis(self):
        self.assertLessEqual(qwen_client._timeout_seconds("general"), 15)
        self.assertLessEqual(qwen_client._timeout_seconds("fast"), 20)
        self.assertLessEqual(qwen_client._total_timeout_seconds("fast"), 35)
        self.assertGreater(qwen_client._total_timeout_seconds("deep"), qwen_client._total_timeout_seconds("fast"))


if __name__ == "__main__":
    unittest.main()

