"""Regression tests for conservative employment work-mode filtering."""
import unittest

from profit_ranker import _work_format_rejection, _work_mode, rank_lead


class WorkModePolicyTests(unittest.TestCase):
    def test_hh_missing_work_mode_is_unknown_not_remote(self):
        lead = {"source": "hh", "title": "Junior Frontend Developer"}
        self.assertEqual(_work_mode(lead), "unknown")
        self.assertEqual(
            _work_format_rejection(lead),
            "remote work format is not confirmed",
        )

    def test_explicit_remote_is_allowed(self):
        lead = {"source": "hh", "work_mode": "remote"}
        self.assertEqual(_work_mode(lead), "remote")
        self.assertIsNone(_work_format_rejection(lead))

    def test_office_is_rejected(self):
        lead = {"source": "hh", "work_mode": "office"}
        self.assertEqual(
            _work_format_rejection(lead),
            "office work is excluded; fully remote only",
        )

    def test_hybrid_only_in_yekaterinburg(self):
        outside = {
            "source": "hh",
            "work_mode": "hybrid",
            "city": "Moscow",
        }
        yekaterinburg = {
            "source": "hh",
            "work_mode": "hybrid",
            "city": "Екатеринбург",
        }
        self.assertEqual(
            _work_format_rejection(outside),
            "hybrid is allowed only in Yekaterinburg",
        )
        self.assertIsNone(_work_format_rejection(yekaterinburg))

    def test_remote_only_source_can_infer_remote(self):
        lead = {"source": "remoteok"}
        self.assertEqual(_work_mode(lead), "remote")
        self.assertIsNone(_work_format_rejection(lead))

    def test_freelance_does_not_use_employment_work_mode_gate(self):
        lead = {"source": "freelancer_com"}
        self.assertIsNone(_work_format_rejection(lead))

    def test_company_based_in_russia_is_not_proof_of_candidate_eligibility(self):
        from profit_ranker import _location_rejected, _text
        lead = {
            "source": "remoteok",
            "title": "Junior React Developer",
            "location": "Worldwide",
            "description": "Our company is based in Russia. We welcome applicants worldwide.",
        }
        self.assertTrue(_location_rejected(lead, _text(lead)))

    def test_explicit_candidate_residence_in_russia_is_accepted(self):
        from profit_ranker import _location_rejected, _text
        lead = {
            "source": "remoteok",
            "title": "Junior React Developer",
            "location": "Worldwide",
            "description": "Candidates must reside in Russia.",
        }
        self.assertFalse(_location_rejected(lead, _text(lead)))

    def test_junior_signal_in_description_is_recognized(self):
        lead = {
            "source": "hh",
            "title": "Frontend Developer",
            "description": "Junior position. React and JavaScript.",
            "work_mode": "remote",
            "location": "Россия",
            "salary": {"from": 60000, "to": 60000, "currency": "RUB", "period": "month"},
        }
        ranked = rank_lead(lead)
        self.assertNotEqual(ranked.get("rank_reason"), "not Junior or 0-3 years")
        self.assertTrue(ranked.get("eligible"))


if __name__ == "__main__":
    unittest.main()
