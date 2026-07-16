import asyncio
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

    def test_technology_market_news_preserves_sector_intent(self):
        route = self.assert_route("Give me the latest technology market news", "headlines")
        self.assertEqual(route["category"], "Stocks")
        self.assertEqual(route["topic"], "technology")

    def test_company_fallback_adds_fact_grounded_trend_and_risk_signals(self):
        facts = {
            "ticker": "TEST",
            "company_name": "Test Company",
            "market_data": {"trailing_pe": "30.00x", "forward_pe": "20.00x"},
            "financial_metrics": {
                "revenue_growth": "25.00%",
                "operating_margin": "35.00%",
                "operating_cashflow": "100.00",
                "free_cashflow": "80.00",
                "debt_to_equity": "15.00%",
            },
        }

        content = main.build_company_facts_fallback("Analyze TEST", facts, "unused")

        self.assertIn("**Key risks and watch items**", content)
        self.assertIn("Growth: revenue growth of 25.00% is strong", content)
        self.assertIn("Cash conversion: free cash flow equals 80.0%", content)
        self.assertIn("Balance-sheet risk: debt/equity of 15.00% indicates low", content)
        self.assertIn("Valuation expectation: forward P/E of 20.00x is below trailing P/E", content)
        self.assertNotIn("Coverage note", content)
        self.assertNotIn("no single metric is a complete investment verdict", content)
        self.assertNotIn("A stronger investment call would require", content)

    def test_internal_ticker_scope_warning_is_not_shown_in_answer(self):
        content = "**Investment view**\nAlibaba has improving operating momentum."
        review = main.AgentRiskReview(
            status="review",
            warnings=["Model answer mentioned extra ticker-like symbols outside the requested scope: ALL"],
            missing_data=[],
            allowed_tickers=["BABA"],
        )

        result = main.finalize_agent_content(content, review)

        self.assertEqual(result, content)
        self.assertNotIn("Caveat", result)
        self.assertNotIn("extra ticker-like symbols", result)

    def test_comparison_fallback_explains_profitability_cash_and_leverage_tradeoffs(self):
        facts = {
            "LEFT": {"financial_metrics": {"operating_margin": "20.00%", "free_cashflow": "120", "debt_to_equity": "70.00%"}, "market_data": {"price_to_book": "10.00x"}},
            "RIGHT": {"financial_metrics": {"operating_margin": "35.00%", "free_cashflow": "90", "debt_to_equity": "20.00%"}, "market_data": {"price_to_book": "6.00x"}},
        }

        content = main.build_comparison_facts_fallback("Compare LEFT and RIGHT", {"tickers": ["LEFT", "RIGHT"]}, facts, "unused")

        self.assertIn("**Interpretation**", content)
        self.assertIn("RIGHT has the higher operating margin", content)
        self.assertIn("LEFT reports the higher free cash flow", content)
        self.assertIn("RIGHT has the lower reported debt/equity", content)

    def test_plain_english_or_does_not_create_a_false_ticker_scope_warning(self):
        review = main.run_agent_risk_review(
            {"kind": "comparison", "tickers": ["AAPL", "MSFT"]},
            {"AAPL": {"data_status": "available"}, "MSFT": {"data_status": "available"}},
            "Choose whether you prioritize stronger margins or higher cash generation.",
        )

        self.assertEqual(review.warnings, [])
        with patch.dict(main.ALIASES, {"or": "OR.PA"}, clear=True):
            self.assertNotIn("OR.PA", main.extract_symbol_candidates("Cash flow or operating margin"))
        self.assertIn("OR.PA", main.extract_symbol_candidates("Compare $OR with AAPL"))

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
        self.assertIn("| Last price | 200.0 |", answer)
        self.assertIn("| Gross margin | 46.00% |", answer)
        self.assertNotIn("Unavailable in supplied backend data", answer)

    def test_standard_fallbacks_hide_methodology_and_source_boilerplate(self):
        company = main.build_company_facts_fallback(
            "Analyze AAPL",
            {
                "ticker": "AAPL",
                "company_name": "Apple",
                "market_data": {"last_price": 200.0},
                "financial_metrics": {},
                "source": "test provider",
            },
            "fallback",
        )
        comparison = main.build_comparison_facts_fallback(
            "Compare AAA and BBB",
            {"tickers": ["AAA", "BBB"]},
            {"AAA": {}, "BBB": {}},
            "fallback",
        )
        self.assertNotIn("Methodology", company)
        self.assertNotIn("Data source", company)
        self.assertNotIn("Methodology", comparison)

    def test_data_sources_are_available_only_when_explicitly_requested(self):
        route = main.classify_message("Where does QFin get its data?")
        self.assertEqual(route["kind"], "data_sources")
        result = asyncio.run(main.generate_agent_reply("Where does QFin get its data?"))
        self.assertIn("**Data sources**", result["content"])
        self.assertIn("Supabase warehouse", result["content"])

    def test_attachment_fallback_hides_methodology_boilerplate(self):
        result = main.build_spreadsheet_attachment_fallback(
            {
                "filename": "financials.csv",
                "sheets": ["CSV"],
                "rows": 2,
                "table_data": [],
            }
        )
        self.assertNotIn("Methodology", result)

    def test_forum_comments_are_saved_and_returned_with_the_thread(self):
        main.FORUM_THREADS.clear()
        main.FORUM_COMMENTS.clear()
        thread = main.create_forum_thread_record(
            main.ForumCreateRequest(title="Test thread", body="Looking for views.", author="Starter")
        )["thread"]
        created = main.create_forum_comment_record(
            thread["id"],
            main.ForumCommentCreateRequest(body="Here is a useful perspective.", author="Responder"),
        )
        self.assertEqual(created["status"], "created")
        state = main.load_forum_threads()
        loaded = next(item for item in state["threads"] if item["id"] == thread["id"])
        self.assertEqual(loaded["comment_count"], 1)
        self.assertEqual(loaded["comments"][0]["author"], "Responder")

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

    def test_finance_concept_fallback_hides_internal_fallback_caveat(self):
        answer = main.build_finance_concept_fallback(
            "Explain WACC",
            "Deterministic finance guidance was used to keep the response grounded and time-bounded.",
        )
        self.assertNotIn("**Caveat**", answer)
        self.assertNotIn("Deterministic finance guidance", answer)


class FinanceEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_finance_concept_uses_model_first(self):
        with (
            patch("main.qwen_is_configured", return_value=True),
            patch("main.ask_qwen", new=AsyncMock()) as ask_qwen,
        ):
            ask_qwen.return_value = "## In plain English\n\nWACC is the blended required return."
            answer = await main.build_finance_response(
                "Explain WACC",
                {"kind": "finance_concept", "detail": "standard"},
                {},
            )

        ask_qwen.assert_awaited_once()
        self.assertIn("WACC", answer)

    async def test_standard_comparison_uses_model_first(self):
        facts = {
            "AAA": {"market_data": {"forward_pe": "20.00x"}, "financial_metrics": {}},
            "BBB": {"market_data": {"forward_pe": "15.00x"}, "financial_metrics": {}},
        }
        with (
            patch("main.qwen_is_configured", return_value=True),
            patch("main.ask_qwen", new=AsyncMock()) as ask_qwen,
        ):
            ask_qwen.return_value = "## Bottom line\n\nBBB has the lower supplied forward P/E."
            answer = await main.build_finance_response(
                "Compare AAA and BBB",
                {"kind": "comparison", "tickers": ["AAA", "BBB"], "detail": "standard"},
                facts,
            )
        ask_qwen.assert_awaited_once()
        self.assertIn("BBB", answer)

    def test_finance_answer_normalizer_repairs_glm_heading_drift(self):
        answer = main.normalize_finance_answer(
            "**Q**\n**Direct answer** Alibaba has improving cash generation.\n\n**Key risks**\nCompetition remains intense.",
            "company",
        )
        self.assertTrue(answer.startswith("## Investment view"), answer)
        self.assertIn("## Key risks", answer)
        self.assertNotIn("**Q**", answer)
        self.assertNotIn("**Direct answer**", answer)

    def test_finance_answer_normalizer_preserves_words_starting_with_labels(self):
        quarterly = main.normalize_finance_answer("Quarterly earnings improved.", "company")
        answering = main.normalize_finance_answer("Answering your question requires two steps.", "finance_concept")
        investor_qa = main.normalize_finance_answer("## Q&A for investors\n\nWhat changed this quarter?", "company")
        self.assertTrue(quarterly.endswith("Quarterly earnings improved."))
        self.assertTrue(answering.endswith("Answering your question requires two steps."))
        self.assertIn("## Q&A for investors", investor_qa)

    def test_finance_answer_normalizer_handles_markdown_labels_and_methodology(self):
        answer = main.normalize_finance_answer(
            "## Q\n\n## Direct answer\nAlibaba is profitable.\n\n## Methodology\nInternal routing details.\n\n## Verdict\nWatch cash flow.",
            "company",
        )
        self.assertTrue(answer.startswith("## Investment view"), answer)
        self.assertNotIn("Methodology", answer)
        self.assertIn("## Verdict", answer)

    def test_explicit_methodology_request_preserves_methodology_section(self):
        content = "## Investment view\n\nAlibaba is profitable.\n\n## Methodology\nUsed supplied financial facts."
        answer = main.normalize_finance_answer(content, "company", preserve_methodology=True)
        self.assertIn("## Methodology", answer)
        self.assertTrue(main.user_requests_methodology("Analyze Alibaba and explain your methodology"))

    async def test_incomplete_provider_response_uses_client_error(self):
        with patch("main.call_qwen", new=AsyncMock(return_value={"choices": []})):
            with self.assertRaises(main.QwenClientError):
                await main.ask_qwen([{"role": "user", "content": "Analyze AAPL"}])

    async def test_comparison_outage_fallback_has_one_bottom_line(self):
        facts = {
            "AAA": {"market_data": {"forward_pe": "20.00x"}, "financial_metrics": {}},
            "BBB": {"market_data": {"forward_pe": "15.00x"}, "financial_metrics": {}},
        }
        with patch("main.qwen_is_configured", return_value=False):
            answer = await main.build_finance_response(
                "Compare AAA and BBB",
                {"kind": "comparison", "tickers": ["AAA", "BBB"], "detail": "standard"},
                facts,
            )
        self.assertEqual(answer.count("## Bottom line"), 1)
        self.assertIn("## Side-by-side", answer)
        self.assertIn("## Verdict", answer)

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
            "financial_metrics": {},
            "historical_financials": {},
            "data_status": "available",
        }
        with (
            patch("main.load_warehouse_snapshot", return_value=warehouse),
            patch("main.fmp_is_configured", return_value=False),
            patch("main.fetch_live_market_snapshot_async", new=AsyncMock(return_value=live)) as fetch_live,
        ):
            result = await main.get_company_facts_async("AAPL")

        fetch_live.assert_awaited_once_with("AAPL")
        self.assertEqual(result["market_data"]["last_price"], 200.0)
        self.assertEqual(result["market_data"]["forward_pe"], "25.00x")


class QwenModelRoutingTests(unittest.TestCase):
    def test_general_questions_use_active_dated_qwen_profile_first(self):
        messages = main.build_general_prompt("Explain photosynthesis simply.")
        self.assertEqual(qwen_client._detect_task_type(messages), "general")
        self.assertEqual(qwen_client._model_chain("general")[0], "qwen3.7-plus-2026-05-26")

    def test_default_model_profile_uses_active_dated_models(self):
        with patch.dict(
            qwen_client.os.environ,
            {
                "DASHSCOPE_MODEL": "",
                "DASHSCOPE_MODEL_FAST": "",
                "DASHSCOPE_MODEL_DEEP": "",
                "DASHSCOPE_MODEL_FLASH": "",
                "DASHSCOPE_MODEL_VISION": "",
                "DASHSCOPE_NEWS_MODEL": "",
            },
            clear=False,
        ):
            profile = qwen_client._model_profile()

        self.assertEqual(profile["fast"], "qwen3.7-plus-2026-05-26")
        self.assertEqual(profile["deep"], "qwen3.7-max-2026-05-20")
        self.assertEqual(profile["flash"], "glm-5.1")
        self.assertEqual(profile["vision"], "qwen-vl-plus-latest")
        self.assertEqual(profile["news"], "qwen3.7-plus-2026-05-26")

    def test_stale_render_model_overrides_are_replaced(self):
        with patch.dict(
            qwen_client.os.environ,
            {
                "DASHSCOPE_MODEL": "qwen3.7-plus",
                "DASHSCOPE_MODEL_FAST": "qwen3.7-plus",
                "DASHSCOPE_MODEL_DEEP": "qwen3.7-max",
                "DASHSCOPE_MODEL_FLASH": "qwen3.6-flash",
            },
            clear=False,
        ):
            profile = qwen_client._model_profile()

        self.assertEqual(profile["fast"], "qwen3.7-plus-2026-05-26")
        self.assertEqual(profile["deep"], "qwen3.7-max-2026-05-20")
        self.assertEqual(profile["flash"], "glm-5.1")
        self.assertNotIn("qwen3.7-plus", qwen_client._model_chain("general"))

    def test_text_failover_chain_uses_exact_active_models_then_glm(self):
        with patch.dict(qwen_client.os.environ, {}, clear=True):
            self.assertEqual(
                qwen_client._model_chain("deep"),
                [
                    "qwen3.7-max-2026-05-20",
                    "qwen3.7-max-2026-05-17",
                    "deepseek-v4-pro",
                    "glm-5.2",
                    "glm-5.1",
                    "qwen3.7-plus-2026-05-26",
                ],
            )

    def test_standard_company_analysis_uses_fast_profile(self):
        messages = main.build_finance_prompt(
            "Analyze AAPL",
            {"kind": "company", "ticker": "AAPL", "detail": "standard"},
            {"ticker": "AAPL"},
        )
        self.assertEqual(qwen_client._detect_task_type(messages), "fast")

    def test_backend_fact_words_do_not_promote_standard_analysis_to_deep(self):
        messages = main.build_finance_prompt(
            "Analyze AAPL",
            {"kind": "company", "ticker": "AAPL", "detail": "standard"},
            {
                "ticker": "AAPL",
                "note": "Source includes a comprehensive annual financial report.",
            },
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
        with patch.dict(qwen_client.os.environ, {}, clear=True):
            self.assertEqual(qwen_client._timeout_seconds("general"), 30)
            self.assertEqual(qwen_client._timeout_seconds("fast"), 60)
            self.assertEqual(qwen_client._total_timeout_seconds("fast"), 120)
            self.assertEqual(qwen_client._total_timeout_seconds("deep"), 180)
            self.assertGreater(qwen_client._total_timeout_seconds("deep"), qwen_client._total_timeout_seconds("fast"))

    def test_news_route_uses_news_profile_before_standard_depth(self):
        messages = main.build_finance_prompt(
            "What happened in stock markets?",
            {"kind": "news", "category": "Stocks", "detail": "standard"},
            {"news": []},
        )
        self.assertEqual(qwen_client._detect_task_type(messages), "news")

    def test_timeout_environment_can_expand_within_safe_ceiling(self):
        with patch.dict(
            qwen_client.os.environ,
            {
                "AI_PROVIDER_TIMEOUT_SECONDS_DEEP": "175",
                "AI_PROVIDER_TOTAL_TIMEOUT_SECONDS_DEEP": "280",
            },
            clear=False,
        ):
            self.assertEqual(qwen_client._timeout_seconds("deep"), 175)
            self.assertEqual(qwen_client._total_timeout_seconds("deep"), 280)

    def test_model_quota_error_can_fail_over_but_bad_credentials_cannot(self):
        self.assertFalse(qwen_client._is_terminal_api_status(403))
        self.assertTrue(qwen_client._is_terminal_api_status(401))

    def test_finance_facts_are_serialized_compactly_for_the_model(self):
        serialized = main.serialize_agent_facts({"ticker": "AAPL", "metrics": {"margin": "30%"}})
        self.assertNotIn("\n", serialized)
        self.assertIn('"ticker":"AAPL"', serialized)
        self.assertEqual(qwen_client._max_tokens("fast"), 6000)
        self.assertEqual(qwen_client._max_tokens("deep"), 12000)

    def test_recent_model_failures_are_cooled_down_per_task(self):
        qwen_client.MODEL_COOLDOWNS.clear()
        qwen_client._defer_model("fast", "qwen3.6-flash", 300, now=100)

        self.assertFalse(qwen_client._model_is_available("fast", "qwen3.6-flash", now=250))
        self.assertTrue(qwen_client._model_is_available("general", "qwen3.6-flash", now=250))
        self.assertTrue(qwen_client._model_is_available("fast", "qwen3.6-flash", now=400))

    def test_quota_cooldown_skips_model_for_every_task(self):
        qwen_client.MODEL_COOLDOWNS.clear()
        qwen_client._defer_model("quota", "qwen3.7-plus-2026-05-26", 300, now=100)

        self.assertFalse(qwen_client._model_is_available("fast", "qwen3.7-plus-2026-05-26", now=250))
        self.assertFalse(qwen_client._model_is_available("news", "qwen3.7-plus-2026-05-26", now=250))
        self.assertTrue(qwen_client._model_is_available("fast", "qwen3.7-plus-2026-05-26", now=400))

    def test_quota_errors_are_detected_without_treating_other_403s_as_quota(self):
        self.assertTrue(qwen_client._is_quota_error(403, "AllocationQuota exhausted"))
        self.assertTrue(qwen_client._is_quota_error(400, "AllocationQuota exhausted"))
        self.assertTrue(qwen_client._is_quota_error(429, "insufficient_quota"))
        self.assertFalse(qwen_client._is_quota_error(403, "Model access denied"))


class FinancialDataConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        main.FINANCIAL_DATA_CACHE.clear()
        main.FINANCIAL_DATA_INFLIGHT.clear()
        main.LIVE_MARKET_CACHE.clear()
        main.LIVE_MARKET_INFLIGHT.clear()

    async def asyncTearDown(self):
        main.FINANCIAL_DATA_CACHE.clear()
        main.FINANCIAL_DATA_INFLIGHT.clear()
        main.LIVE_MARKET_CACHE.clear()
        main.LIVE_MARKET_INFLIGHT.clear()

    async def test_concurrent_requests_share_one_provider_fetch(self):
        calls = 0

        async def fake_to_thread(function, ticker):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {"ticker": ticker, "data_status": "available", "market_data": {"last_price": 100}}

        with patch("main.asyncio.to_thread", side_effect=fake_to_thread):
            results = await asyncio.gather(
                main.fetch_financial_data_async("AAPL"),
                main.fetch_financial_data_async("aapl"),
                main.fetch_financial_data_async(" AAPL "),
            )

        self.assertEqual(calls, 1)
        self.assertEqual([result["ticker"] for result in results], ["AAPL", "AAPL", "AAPL"])

    async def test_transient_failure_is_not_cached(self):
        with patch(
            "main.asyncio.to_thread",
            new=AsyncMock(return_value={"ticker": "AAPL", "data_status": "unavailable"}),
        ):
            await main.fetch_financial_data_async("AAPL")

        self.assertNotIn("AAPL", main.FINANCIAL_DATA_CACHE)

    async def test_company_facts_starts_warehouse_and_live_reads_together(self):
        warehouse_started = asyncio.Event()
        live_started = asyncio.Event()

        async def fake_to_thread(function, ticker):
            if function is main.load_warehouse_snapshot:
                warehouse_started.set()
                await live_started.wait()
                return {"symbol": ticker, "status": "unavailable"}
            if function is main.fetch_live_market_snapshot:
                live_started.set()
                await warehouse_started.wait()
                return {"ticker": ticker, "data_status": "available", "market_data": {"last_price": 100}}
            raise AssertionError(f"Unexpected threaded function: {function}")

        with (
            patch("main.asyncio.to_thread", side_effect=fake_to_thread),
            patch("main.fmp_is_configured", return_value=False),
            patch("main.warehouse_snapshot_is_usable", return_value=True),
        ):
            result = await main.get_company_facts_async("AAPL")

        self.assertEqual(result["market_data"]["last_price"], 100)


class FinanceFallbackTests(unittest.TestCase):
    def test_core_finance_topics_have_specific_deterministic_answers(self):
        prompts_and_markers = [
            ("Explain IRR", "multiple IRRs"),
            ("Explain EV/EBITDA", "Enterprise value"),
            ("Explain price to book", "book value per share"),
            ("Explain ROIC", "NOPAT"),
            ("Explain the Sharpe ratio", "standard deviation"),
            ("Explain the Sortino ratio", "downside deviation"),
            ("Explain Value at Risk", "expected shortfall"),
            ("Explain CAPM", "equity risk premium"),
            ("Explain credit spreads", "option-adjusted"),
            ("Explain option Greeks", "Gamma"),
            ("Explain diversification", "correlation"),
            ("How does inflation affect investments?", "purchasing power"),
            ("Explain working capital", "use of cash"),
            ("How do financial statements connect?", "retained earnings"),
            ("Explain diluted EPS", "potential dilution"),
            ("Explain dividend yield", "expected cut"),
            ("Explain financial leverage", "refinancing risk"),
            ("Explain the current ratio", "current assets"),
            ("Explain CAGR", "ending value"),
            ("Explain terminal value", "Perpetuity growth"),
            ("Explain equity beta", "systematic risk"),
            ("Explain futures contracts", "marked to market"),
        ]
        for prompt, marker in prompts_and_markers:
            with self.subTest(prompt=prompt):
                result = main.build_finance_concept_fallback(prompt, "deterministic guidance")
                self.assertIn(marker, result)

    def test_emergency_fund_uses_supplied_monthly_spending(self):
        result = main.build_finance_concept_fallback(
            "Build an emergency fund plan for $2,000 monthly spending.",
            "deterministic guidance",
        )
        self.assertIn("$6,000", result)
        self.assertIn("$12,000", result)
        self.assertIn("$24,000", result)

    def test_bank_fallback_uses_sector_appropriate_metrics(self):
        facts = {
            "ticker": "BBCA.JK",
            "company_name": "Bank Central Asia",
            "market_data": {
                "last_price": 6175,
                "trailing_pe": "13.11x",
                "price_to_book": "2.93x",
                "ev_ebitda": None,
            },
            "financial_metrics": {
                "net_income": "IDR 58.08T",
                "return_on_equity": "22.97%",
                "return_on_assets": "3.66%",
                "ebitda": None,
            },
            "warehouse": {
                "profile": {"sector": "Financial Services", "industry": "Banks - Regional"}
            },
        }
        result = main.build_company_facts_fallback("Analyze BBCA", facts, "fallback")
        self.assertIn("For a bank", result)
        self.assertNotIn("EV/EBITDA", result)
        self.assertNotIn("Coverage note", result)

    def test_known_single_letter_reit_symbol_routes_correctly(self):
        route = main.classify_message("Analyze O")
        self.assertEqual(route["kind"], "company")
        self.assertEqual(route["ticker"], "O")

    def test_reit_fallback_uses_property_metrics(self):
        facts = {
            "ticker": "O",
            "company_name": "Realty Income Corporation",
            "market_data": {
                "last_price": 60.0,
                "market_cap": "USD 55.00B",
                "dividend_yield": "5.50%",
            },
            "financial_metrics": {
                "total_revenue": "USD 5.00B",
                "operating_cashflow": "USD 3.00B",
                "total_debt": "USD 26.00B",
            },
            "warehouse": {
                "profile": {"sector": "Real Estate", "industry": "REIT - Retail"}
            },
        }
        result = main.build_company_facts_fallback("Analyze O", facts, "fallback")
        self.assertIn("For a REIT", result)
        self.assertIn("Operating cash flow", result)
        self.assertNotIn("EV/EBITDA", result)
        self.assertNotIn("Coverage note", result)

    def test_insurer_fallback_uses_underwriting_metrics(self):
        facts = {
            "ticker": "PGR",
            "company_name": "Progressive Corporation",
            "market_data": {
                "last_price": 250.0,
                "trailing_pe": "18.00x",
                "price_to_book": "5.00x",
            },
            "financial_metrics": {
                "total_revenue": "USD 80.00B",
                "net_income": "USD 8.00B",
                "return_on_equity": "30.00%",
            },
            "warehouse": {
                "profile": {"sector": "Financial Services", "industry": "Insurance - Property & Casualty"}
            },
        }
        result = main.build_company_facts_fallback("Analyze PGR", facts, "fallback")
        self.assertIn("For an insurer", result)
        self.assertNotIn("EV/EBITDA", result)
        self.assertNotIn("Gross margin", result)
        self.assertNotIn("Coverage note", result)

    def test_etf_fallback_uses_fund_metrics_and_correct_distribution_yield(self):
        warehouse = {
            "status": "available",
            "profile": {
                "company_name": "State Street SPDR S&P 500 ETF",
                "provider_payload": {
                    "profile": {
                        "isEtf": True,
                        "lastDividend": 7.525,
                        "price": 754.95,
                    }
                },
            },
        }
        live = {
            "company_name": "State Street SPDR S&P 500 ETF",
            "currency": "USD",
            "market_data": {
                "last_price": 754.95,
                "market_cap": "USD 692.88B",
                "dividend_yield": "101.00%",
            },
            "financial_metrics": {},
            "historical_financials": {},
            "data_status": "available",
        }
        merged = main.merge_financial_facts("SPY", warehouse, live)
        result = main.build_company_facts_fallback("Analyze SPY", merged, "fallback")
        self.assertEqual(merged["market_data"]["dividend_yield"], "1.00%")
        self.assertIn("For an ETF or fund", result)
        self.assertIn("Fund size / market value", result)
        self.assertNotIn("Fundamentals", result)
        self.assertNotIn("Coverage note", result)


if __name__ == "__main__":
    unittest.main()


