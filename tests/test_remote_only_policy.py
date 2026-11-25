"""Regression tests for the candidate's remote-only work-mode policy."""
import unittest

from profit_ranker import _location_rejected, _work_format_rejection


class RemoteOnlyPolicyTests(unittest.TestCase):
    def test_fully_remote_is_allowed(self):
        self.assertIsNone(_work_format_rejection({
            "source": "hh",
            "title": "Junior React Developer",
            "work_mode": "remote",
        }))

    def test_hybrid_is_rejected_even_in_yekaterinburg(self):
        self.assertEqual(
            _work_format_rejection({
                "source": "hh",
                "title": "Junior React Developer",
                "location": "Екатеринбург",
                "work_mode": "hybrid",
            }),
            "hybrid roles are excluded; fully remote is required",
        )

    def test_office_and_unconfirmed_modes_are_rejected(self):
        self.assertEqual(
            _work_format_rejection({"source": "other", "work_mode": "office"}),
            "office/on-site roles are excluded",
        )
        self.assertEqual(
            _work_format_rejection({"source": "other", "work_mode": "unknown"}),
            "remote work format is not confirmed",
        )

    def test_generic_work_authorization_mention_is_not_an_auto_rejection(self):
        lead = {
            "source": "remotive",
            "location": "Worldwide",
            "title": "Junior React Developer",
            "description": "Remote role; accepts applicants residing in Russia. Work authorization information may be requested.",
        }
        self.assertFalse(_location_rejected(lead, " ".join(lead.values())))

    def test_explicit_eu_right_to_work_requirement_is_rejected(self):
        lead = {
            "source": "remotive",
            "location": "Worldwide",
            "title": "Junior React Developer",
            "description": "Applicants must have the right to work in the EU.",
        }
        self.assertTrue(_location_rejected(lead, " ".join(lead.values())))


if __name__ == "__main__":
    unittest.main()
