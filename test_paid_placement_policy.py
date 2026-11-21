import unittest
import tempfile
import os

from direct_outreach import build_outreach_draft, build_outreach_drafts
from profit_ranker import rank_lead
from main import ok as hh_listing_is_eligible


class PaidPlacementPolicyTests(unittest.TestCase):
    def test_paid_remote_frontend_internship_is_eligible_and_prioritized(self):
        lead = rank_lead({
            "title": "Frontend Developer Intern",
            "company": "Example Labs",
            "source": "hh",
            "location": "Россия",
            "salary": "Стажировка оплачиваемая, 40 000 ₽ в месяц",
            "description": "Оплачиваемая стажировка. JavaScript, HTML, CSS.",
            "experience": "Без опыта",
        })
        self.assertTrue(lead["eligible"], lead.get("rank_reason"))
        self.assertEqual(lead["opportunity_type"], "paid_placement")

    def test_hh_collection_keeps_paid_placement_and_rejects_unpaid(self):
        paid = {
            "name": "Frontend Developer Intern",
            "salary": {"from": 30000, "currency": "RUR"},
            "snippet": {"requirement": "JavaScript, HTML, CSS"},
        }
        unpaid = {
            "name": "Frontend Developer Intern",
            "snippet": {"requirement": "JavaScript, HTML, CSS. Неоплачиваемая стажировка"},
        }
        junior = {
            "name": "Junior Frontend Developer",
            "snippet": {"requirement": "JavaScript, HTML, CSS"},
        }
        self.assertTrue(hh_listing_is_eligible(paid))
        self.assertFalse(hh_listing_is_eligible(unpaid))
        self.assertTrue(hh_listing_is_eligible(junior))

    def test_unpaid_or_unconfirmed_placement_is_rejected(self):
        for description in ("Неоплачиваемая стажировка", "Стажировка, условия оплаты не указаны"):
            lead = rank_lead({
                "title": "Frontend Developer Intern",
                "company": "Example Labs",
                "source": "hh",
                "location": "Россия",
                "description": description + ". JavaScript, HTML, CSS.",
            })
            if "неоплачиваемая" in description.lower():
                self.assertFalse(lead["eligible"])
            else:
                self.assertTrue(lead["eligible"])
                self.assertTrue(lead["salary_review_required"])

    def test_ordinary_junior_without_salary_is_held_for_manual_review(self):
        lead = rank_lead({
            "title": "Junior Frontend Developer",
            "company": "Example Labs",
            "source": "hh",
            "location": "Россия",
            "experience": "Без опыта",
            "description": "JavaScript, HTML, CSS. Опыт не требуется.",
        })
        self.assertTrue(lead["eligible"], lead.get("rank_reason"))
        self.assertTrue(lead["salary_review_required"])

    def test_regular_salary_bounds_are_50k_to_70k_monthly(self):
        for amount in (50000, 60000, 70000):
            lead = rank_lead({"title":"Junior Frontend Developer","source":"hh","location":"Россия","experience":"Без опыта","salary":{"from":amount,"currency":"RUR"},"description":"JavaScript, HTML, CSS."})
            self.assertTrue(lead["eligible"], lead.get("rank_reason"))
        for amount in (49000, 71000):
            lead = rank_lead({"title":"Junior Frontend Developer","source":"hh","location":"Россия","experience":"Без опыта","salary":{"from":amount,"currency":"RUR"},"description":"JavaScript, HTML, CSS."})
            self.assertFalse(lead["eligible"])

    def test_internship_salary_bounds_are_30k_to_70k_monthly(self):
        for amount in (30000, 45000, 70000):
            lead = rank_lead({"title":"Frontend Developer Intern","source":"hh","location":"Россия","salary":{"from":amount,"currency":"RUR"},"description":"Оплачиваемая стажировка. JavaScript, HTML, CSS.","experience":"Без опыта"})
            self.assertTrue(lead["eligible"], lead.get("rank_reason"))
        for amount in (29000, 71000):
            lead = rank_lead({"title":"Frontend Developer Intern","source":"hh","location":"Россия","salary":{"from":amount,"currency":"RUR"},"description":"Оплачиваемая стажировка. JavaScript, HTML, CSS.","experience":"Без опыта"})
            self.assertFalse(lead["eligible"])

    def test_salary_range_crossing_bounds_requires_manual_review(self):
        lead = rank_lead({"title":"Junior Frontend Developer","source":"hh","location":"Россия","experience":"Без опыта","salary":{"from":45000,"to":60000,"currency":"RUR"},"description":"JavaScript, HTML, CSS."})
        self.assertTrue(lead["eligible"])
        self.assertTrue(lead["salary_review_required"])

    def test_annual_rub_salary_is_normalized_to_monthly(self):
        lead = rank_lead({"title":"Junior Frontend Developer","source":"hh","location":"Россия","experience":"Без опыта","salary":{"from":600000,"currency":"RUR","period":"year"},"description":"JavaScript, HTML, CSS."})
        self.assertTrue(lead["eligible"], lead.get("rank_reason"))

    def test_hybrid_is_rejected_even_in_yekaterinburg(self):
        lead = rank_lead({
            "title": "Junior Frontend Developer",
            "company": "Example Labs",
            "source": "hh",
            "location": "Екатеринбург",
            "work_mode": "hybrid",
            "experience": "Без опыта",
            "description": "JavaScript, HTML, CSS.",
        })
        self.assertFalse(lead["eligible"])
        self.assertEqual(lead["rank_reason"], "hybrid work is excluded; fully remote only")

    def test_excluded_employers_are_rejected(self):
        for company in ("ASTON", "PREAX", "Edmagit"):
            lead = rank_lead({
                "title": "Junior Frontend Developer",
                "company": company,
                "source": "hh",
                "location": "Россия",
                "experience": "Без опыта",
                "description": "JavaScript, HTML, CSS.",
            })
            self.assertFalse(lead["eligible"])
            self.assertEqual(lead["rank_reason"], "excluded employer")

    def test_outreach_drafts_cover_both_opportunity_types_and_skip_excluded(self):
        internship = build_outreach_draft({
            "title": "Frontend Developer Intern",
            "company": "Example Labs",
        })
        junior = build_outreach_draft({
            "title": "Junior Frontend Developer",
            "company": "Example Labs",
        })
        excluded = build_outreach_draft({
            "title": "Junior Frontend Developer",
            "company": "Edmagit",
        })
        self.assertEqual(internship["opportunity_type"], "paid_placement")
        self.assertIn("оплачиваемую стажировку", internship["message_draft"])
        self.assertEqual(junior["opportunity_type"], "junior_vacancy")
        self.assertIn("Junior Frontend Developer", junior["message_draft"])
        self.assertIsNone(excluded)
        drafts = build_outreach_drafts([
            {"title": "Frontend Developer Intern", "company": "Example Labs"},
            {"title": "Junior Frontend Developer", "company": "Example Labs"},
        ])
        self.assertEqual(len(drafts), 2)

    def test_outreach_ledger_lifecycle_and_followup(self):
        import queue_store
        from queue_store import save_outreach_drafts, update_outreach_status, list_outreach
        with tempfile.TemporaryDirectory() as tmp:
            old = queue_store.DB_PATH
            queue_store.DB_PATH = os.path.join(tmp, "test.db")
            try:
                draft = build_outreach_draft({
                    "title": "Junior Frontend Developer",
                    "company": "Example Labs",
                    "url": "https://example.com/jobs/1",
                })
                oid = save_outreach_drafts([draft])[0]
                self.assertEqual(list_outreach()[0]["status"], "DRAFT")
                update_outreach_status(oid, "CONTACTED", follow_up_days=7)
                self.assertEqual(list_outreach()[0]["status"], "CONTACTED")
                update_outreach_status(oid, "REPLIED")
                self.assertEqual(list_outreach()[0]["status"], "REPLIED")
                with self.assertRaises(ValueError):
                    update_outreach_status(oid, "INVALID")
            finally:
                queue_store.DB_PATH = old


if __name__ == "__main__":
    unittest.main()
