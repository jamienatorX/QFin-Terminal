import unittest
from unittest.mock import patch

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
        self.assert_route("Explain photosynthesis to a 12-year-old.", "general")
        self.assert_route("What is AI and how does it work?", "general")
        self.assert_route("What does NASA do?", "general")

    def test_finance_acronyms_are_concepts_not_tickers(self):
        self.assert_route("Explain WACC, its formula, and when it is used.", "finance_concept")
        self.assert_route("How does a DCF valuation work?", "finance_concept")
        self.assert_route("What is ROE and how should I interpret it?", "finance_concept")
        self.assert_route("Build an emergency fund plan for $2,000 monthly spending.", "finance_concept")

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

    def test_blank_input_becomes_fast_greeting(self):
        payload = main.AgentChatRequest(message="   ")
        self.assertEqual(main.extract_chat_query(payload), "Hello")

    def test_exchange_suffix_is_required_for_warehouse_identity(self):
        self.assertTrue(main.warehouse_row_matches_symbol({"provider_symbol": "BBCA.JK"}, "BBCA.JK"))
        self.assertFalse(main.warehouse_row_matches_symbol({"provider_symbol": "BBCA"}, "BBCA.JK"))
        self.assertEqual(financial_data_warehouse._symbol_candidates("BBCA.JK"), ["BBCA.JK"])


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


if __name__ == "__main__":
    unittest.main()

