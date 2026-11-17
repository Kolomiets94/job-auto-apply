from unittest.mock import Mock, patch

import main


def _response(payload):
    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_workplace_policy_remote_everywhere_hybrid_only_in_yekaterinburg():
    assert main.workplace_ok({"location": "Москва", "schedule": {"name": "Удаленная работа"}})
    assert main.workplace_ok({"location": "Екатеринбург", "work_mode": "HYBRID"})
    assert not main.workplace_ok({"location": "Москва", "work_mode": "HYBRID"})
    assert not main.workplace_ok({"location": "Екатеринбург", "schedule": {"name": "Полный день"}})
    assert not main.workplace_ok({
        "location": "Екатеринбург",
        "schedule": {"name": "Удаленная работа"},
        "name": "Junior React Developer офис",
    })


def test_hh_hybrid_search_uses_yekaterinburg_and_hybrid_format():
    payload = {
        "items": [{
            "name": "Junior React Developer",
            "employer": {"name": "Example"},
            "alternate_url": "https://hh.ru/vacancy/123",
            "published_at": "2026-11-17T10:00:00+0500",
            "salary": None,
            "snippet": {},
            "experience": {"name": "Нет опыта"},
            "area": {"name": "Екатеринбург"},
            "work_format": [{"id": "HYBRID", "name": "Гибридный формат"}],
        }]
    }
    with patch.object(main, "hh_yekaterinburg_area_id", return_value="3"), \
         patch.object(main.requests, "get", return_value=_response(payload)) as get:
        leads = main.hh_hybrid_search("frontend", "junior React")

    assert get.call_args.kwargs["params"]["area"] == "3"
    assert get.call_args.kwargs["params"]["work_format"] == "HYBRID"
    assert leads[0]["work_mode"] == "HYBRID"
    assert leads[0]["location"] == "Екатеринбург"



def test_hybrid_and_office_modes_take_precedence_over_incidental_remote_text():
    assert not main.workplace_ok({
        "location": "Москва",
        "schedule": {"name": "Удаленная работа"},
        "work_mode": "HYBRID",
    })
    assert not main.workplace_ok({
        "location": "Екатеринбург",
        "work_mode": "ON_SITE",
    })
    assert not main.workplace_ok({
        "location": "Екатеринбург",
        "schedule": {"name": "Удаленная работа"},
        "snippet": {"description": "Hybrid schedule; React TypeScript"},
    })
