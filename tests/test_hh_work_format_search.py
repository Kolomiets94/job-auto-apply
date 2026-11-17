from unittest.mock import Mock, patch

import main


def _response(payload):
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    response.headers = {}
    response.raise_for_status.return_value = None
    return response


def _payload():
    return {
        "pages": 1,
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
        }],
    }


def test_hh_remote_search_uses_remote_work_format():
    with patch.object(main.requests, "get", return_value=_response(_payload())) as get:
        leads = main.hh_search("frontend", "junior React")

    assert get.call_args.kwargs["params"]["work_format"] == "REMOTE"
    assert "area" not in get.call_args.kwargs["params"]
    assert leads[0]["work_mode"] == "REMOTE"


def test_hh_hybrid_search_is_scoped_to_yekaterinburg():
    with patch.object(main, "hh_yekaterinburg_area_id", return_value="area-ekt"), \
         patch.object(main.requests, "get", return_value=_response(_payload())) as get:
        leads = main.hh_search_hybrid("frontend", "junior React")

    assert get.call_args.kwargs["params"]["work_format"] == "HYBRID"
    assert get.call_args.kwargs["params"]["area"] == "area-ekt"
    assert leads[0]["work_mode"] == "HYBRID"


def test_hh_filter_does_not_drop_hybrid_title():
    assert main.ok({"name": "Junior React Developer (гибрид)", "snippet": {}})
