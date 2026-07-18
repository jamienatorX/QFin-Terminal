import unittest

from answer_quality import (
    finalize_finance_answer,
    normalize_finance_answer,
    user_requests_methodology,
)


class AnswerQualityContractTests(unittest.TestCase):
    def test_company_answer_repairs_provider_labels_into_qfin_structure(self):
        answer = normalize_finance_answer(
            "**Q**\n**Direct answer** Alibaba has improving cash generation."
            "\n\n**Key risks**\nCompetition remains intense.",
            "company",
        )

        self.assertTrue(answer.startswith("## Investment view\n\n"), answer)
        self.assertIn("## Key risks\n\nCompetition remains intense.", answer)
        self.assertNotIn("**Q**", answer)
        self.assertNotIn("Direct answer", answer)

    def test_methodology_is_hidden_unless_user_requests_it(self):
        content = (
            "## Investment view\n\nAlibaba is profitable."
            "\n\n## Methodology\n\nUsed supplied financial facts."
            "\n\n## Verdict\n\nWatch cash conversion."
        )

        hidden = normalize_finance_answer(content, "company")
        preserved = normalize_finance_answer(content, "company", preserve_methodology=True)

        self.assertNotIn("Methodology", hidden)
        self.assertIn("## Verdict", hidden)
        self.assertIn("## Methodology", preserved)
        self.assertTrue(user_requests_methodology("Where did you get the data?"))
        self.assertFalse(user_requests_methodology("Analyze Alibaba thoroughly"))

    def test_methodology_removal_preserves_a_following_numeric_heading(self):
        content = (
            "## Investment view\n\nRevenue is improving.\n\n"
            "## Methodology\n\nUsed supplied financial facts.\n\n"
            "## 2026 outlook\n\nMargins are expected to remain stable."
        )

        normalized = normalize_finance_answer(content, "company")

        self.assertNotIn("Methodology", normalized)
        self.assertIn("## 2026 outlook", normalized)
        self.assertIn("Margins are expected to remain stable.", normalized)

    def test_common_source_requests_preserve_methodology(self):
        self.assertTrue(user_requests_methodology("Please cite your sources"))
        self.assertTrue(user_requests_methodology("What sources did you use?"))

    def test_internal_diagnostics_and_generic_verdict_are_never_user_facing(self):
        answer = normalize_finance_answer(
            "## Investment view\n\nAlibaba remains profitable."
            "\n\n## Verdict\n\nUse the valuation, growth, profitability, cash-flow, "
            "and leverage measures together; no single metric is a complete investment verdict."
            " A stronger investment call would require comparing these figures against multi-year "
            "growth, segment margins, free-cash-flow durability, and peers."
            "\n\n## Caveat\n\nModel answer mentioned extra ticker-like symbols outside "
            "the requested scope: ALL.",
            "company",
        )

        self.assertNotIn("single metric", answer)
        self.assertNotIn("stronger investment call", answer.lower())
        self.assertNotIn("ticker-like", answer)
        self.assertNotIn("ALL", answer)
        self.assertNotIn("## Caveat", answer)

    def test_internal_fallback_bullet_does_not_leave_an_empty_limitation_section(self):
        answer = normalize_finance_answer(
            "**Market read**\nMarkets are mixed.\n\n"
            "**Caveat**\n- Deterministic finance guidance was used to keep the response grounded and time-bounded.",
            "news",
        )

        self.assertEqual(answer, "## Market read\n\nMarkets are mixed.")
        self.assertNotIn("Data limitations", answer)
        self.assertNotIn("\n-\n", answer)

    def test_empty_provider_output_returns_safe_route_specific_message(self):
        answer = normalize_finance_answer("   ", "company")

        self.assertEqual(
            answer,
            "## Investment view\n\nReliable analysis could not be produced from the available evidence.",
        )

    def test_finalizer_shows_each_real_data_gap_once(self):
        answer = finalize_finance_answer(
            "## Investment view\n\nThe available figures show positive operating cash flow.",
            missing_data=(
                "Historical margin data is unavailable.",
                "Historical margin data is unavailable.",
            ),
        )

        self.assertEqual(answer.count("## Data limitations"), 1)
        self.assertEqual(answer.count("Historical margin data is unavailable."), 1)

    def test_finalizer_consolidates_caveat_and_coverage_gap_sections(self):
        content = (
            "## Investment view\n\nRevenue is improving.\n\n"
            "### Caveat\n\n- Quarterly cash flow was unavailable.\n\n"
            "## Coverage gap\n\nPeer valuation data was unavailable."
        )

        finalized = finalize_finance_answer(
            content,
            missing_data=("Quarterly cash flow was unavailable.",),
        )

        self.assertEqual(finalized.count("## Data limitations"), 1)
        self.assertNotIn("Caveat", finalized)
        self.assertNotIn("Coverage gap", finalized)
        self.assertEqual(finalized.count("Quarterly cash flow was unavailable."), 1)
        self.assertEqual(finalized.count("Peer valuation data was unavailable."), 1)

    def test_normalizer_preserves_legitimate_q_words_and_avoids_duplicate_opening(self):
        quarterly = normalize_finance_answer("Quarterly earnings improved.", "company")
        investor_qa = normalize_finance_answer(
            "## Q&A for investors\n\nWhat changed this quarter?",
            "company",
        )
        already_structured = normalize_finance_answer(
            "## Investment view\n\nAlibaba has durable liquidity.",
            "company",
        )

        self.assertIn("Quarterly earnings improved.", quarterly)
        self.assertIn("## Q&A for investors", investor_qa)
        self.assertEqual(already_structured.count("## Investment view"), 1)

    def test_inline_provider_headings_become_scannable_sections(self):
        answer = normalize_finance_answer(
            "**Direct answer** Alibaba has improving earnings quality.\n\n"
            "**Market snapshot:** Valuation is below its recent peak.\n\n"
            "**Fundamentals** Revenue growth is positive while free cash flow remains uneven.\n\n"
            "**Key risks:** Competition and capital intensity remain material.",
            "company",
        )

        self.assertTrue(answer.startswith("## Investment view\n\n"), answer)
        self.assertIn("## Market snapshot\n\nValuation is below its recent peak.", answer)
        self.assertIn(
            "## Fundamentals\n\nRevenue growth is positive while free cash flow remains uneven.",
            answer,
        )
        self.assertIn(
            "## Key risks\n\nCompetition and capital intensity remain material.",
            answer,
        )
        self.assertNotIn("**Market snapshot:**", answer)

    def test_empty_sections_are_removed_after_boilerplate_cleanup(self):
        answer = normalize_finance_answer(
            "## Investment view\n\nAlibaba remains profitable.\n\n"
            "**Verdict** Use the valuation, growth, profitability, cash-flow, and leverage "
            "measures together; no single metric is a complete investment verdict.",
            "company",
        )

        self.assertEqual(answer, "## Investment view\n\nAlibaba remains profitable.")

    def test_known_headings_use_canonical_qfin_casing(self):
        answer = normalize_finance_answer(
            "## INVESTMENT VIEW\n\nRevenue growth is improving.\n\n"
            "**KEY RISKS:** Competition remains intense.\n\n"
            "### verdict\n\nThe risk-reward is balanced.",
            "company",
        )

        self.assertIn("## Investment view", answer)
        self.assertIn("## Key risks", answer)
        self.assertIn("## Verdict", answer)
        self.assertNotIn("## INVESTMENT VIEW", answer)
        self.assertNotIn("## KEY RISKS", answer)

    def test_duplicate_known_sections_are_merged_without_losing_distinct_evidence(self):
        answer = normalize_finance_answer(
            "## Investment view\n\nAlibaba has improving earnings quality.\n\n"
            "## Key risks\n\n- Competition could pressure margins.\n\n"
            "**Key risks:** Regulatory changes could raise compliance costs.\n\n"
            "## Verdict\n\nThe risk-reward is balanced.",
            "company",
        )

        self.assertEqual(answer.count("## Key risks"), 1)
        self.assertIn("Competition could pressure margins.", answer)
        self.assertIn("Regulatory changes could raise compliance costs.", answer)
        self.assertLess(answer.index("## Key risks"), answer.index("## Verdict"))

    def test_duplicate_section_does_not_repeat_identical_body(self):
        answer = normalize_finance_answer(
            "## Bottom line\n\nAAPL leads on cash generation.\n\n"
            "## BOTTOM LINE\n\nAAPL leads on cash generation.\n\n"
            "## Side-by-side\n\n| Metric | AAPL | MSFT |\n|---|---:|---:|\n| FCF | 1 | 2 |",
            "comparison",
        )

        self.assertEqual(answer.count("## Bottom line"), 1)
        self.assertEqual(answer.count("AAPL leads on cash generation."), 1)


if __name__ == "__main__":
    unittest.main()
