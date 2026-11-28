import main


def test_remote_search_includes_adjacent_frontend_role_aliases():
    expected = {
        ("frontend", "Frontend Developer"),
        ("frontend", "JavaScript Developer"),
        ("frontend", "TypeScript Developer"),
        ("frontend", "Web Developer React"),
        ("frontend", "UI Developer"),
    }
    assert expected.issubset(set(main.QUERIES))


def test_hybrid_search_includes_adjacent_roles_but_remains_separate():
    expected = {
        ("frontend", "Frontend Developer"),
        ("frontend", "JavaScript Developer"),
        ("frontend", "TypeScript Developer"),
        ("frontend", "Web Developer React"),
        ("frontend", "UI Developer"),
    }
    assert expected.issubset(set(main.HYBRID_QUERIES))


def test_broader_discovery_does_not_weaken_seniority_or_stack_exclusions():
    assert not main.ok({"name": "Senior Frontend Developer", "snippet": {}})
    assert not main.ok({"name": "Junior Vue.js Developer", "snippet": {}})
    assert not main.ok({"name": "Junior Angular Developer", "snippet": {}})
    assert main.ok({"name": "Junior React Frontend Developer", "snippet": {}})
