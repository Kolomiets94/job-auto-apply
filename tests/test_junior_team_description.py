import unittest
import main


class JuniorDescriptionTests(unittest.TestCase):
    def test_senior_mentor_does_not_exclude_junior(self):
        vacancy = {'name': 'Junior Frontend Developer', 'snippet': {
            'responsibility': 'Work with senior developers and a team lead on React interfaces'}}
        self.assertTrue(main.ok(vacancy))

    def test_senior_vacancy_stays_excluded(self):
        for title in ('Senior React Developer', 'Middle Frontend', 'Lead Frontend Developer'):
            self.assertFalse(main.ok({'name': title}))

    def test_other_exclusions_remain(self):
        for title in ('Junior Full-Stack Developer', 'Junior React Native Developer', 'Trainee React Developer'):
            self.assertFalse(main.ok({'name': title}))

    def test_salary_floor_remains(self):
        self.assertFalse(main.ok({'name': 'Junior React', 'salary': {'from': 30000, 'currency': 'RUB'}}))


if __name__ == '__main__':
    unittest.main()
