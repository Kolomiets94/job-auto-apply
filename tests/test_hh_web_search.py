from hh_web_search import title_matches_category


def test_junior_plus_is_included():
    assert title_matches_category("Junior+ React Developer", "frontend")


def test_non_entry_level_is_excluded():
    assert not title_matches_category("Senior React Developer", "frontend")


def test_non_target_role_is_excluded():
    assert not title_matches_category("Junior QA Engineer", "frontend")
