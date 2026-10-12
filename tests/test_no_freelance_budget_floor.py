import os
import unittest
from unittest.mock import Mock, patch
import freelancehunt_adapter as fh
from profit_ranker import rank_lead


class NoBudgetFloorTests(unittest.TestCase):
    def bid(self, budget):
        lead = {'source': 'freelancehunt', 'external_id': '123', 'title': 'Вёрстка лендинга', 'budget': budget}
        def response(*args, **kwargs):
            return Mock(status_code=201, json=lambda: {'data': {'id': '456', 'attributes': {'comment': kwargs['json']['comment']}}})
        with patch.dict(os.environ, {'AUTO_FREELANCE_APPLY': '1', 'FREELANCEHUNT_TOKEN': 'dummy'}), \
             patch.object(fh, 'application_time_allowed', return_value=True), \
             patch.object(fh.requests, 'post', side_effect=response) as send:
            result = fh.add_bid(lead, 'Individual proposal')
        return result, send

    def test_small_budgets_and_other_currency_are_submitted(self):
        for currency, amount in (('USD', 5), ('RUB', 100), ('UAH', 100)):
            result, send = self.bid({'amount': amount, 'currency': currency})
            self.assertEqual(result['status'], 'SUBMITTED')
            self.assertEqual(send.call_args.kwargs['json']['budget']['amount'], amount)

    def test_missing_or_invalid_price_does_not_send_invented_quote(self):
        for budget in ({}, {'amount': 0, 'currency': 'USD'}, {'amount': True, 'currency': 'USD'},
                       {'amount': float('nan'), 'currency': 'USD'}):
            result, send = self.bid(budget)
            self.assertEqual(result['reason'], 'bid_price_missing_or_invalid')
            send.assert_not_called()

    def test_freelance_budget_does_not_change_score_or_eligibility(self):
        lead = {'source': 'freelancehunt', 'title': 'React landing page', 'description': 'React HTML CSS'}
        small = rank_lead({**lead, 'budget': {'amount': 1, 'currency': 'USD'}})
        large = rank_lead({**lead, 'budget': {'amount': 10000, 'currency': 'USD'}})
        self.assertTrue(small['eligible'])
        self.assertEqual(small['profit_score'], large['profit_score'])
        self.assertEqual(small['profit_score'], rank_lead(lead)['profit_score'])

    def test_job_salary_floor_remains(self):
        lead = {'source': 'hh', 'title': 'Junior React Developer', 'description': 'React',
                'salary': {'from': 10000, 'currency': 'RUB'}}
        self.assertFalse(rank_lead(lead)['eligible'])
