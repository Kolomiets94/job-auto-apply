from ats_conditions import assess_job_conditions


def test_remote_russia_and_paid_placement_are_confirmed_only_with_evidence():
    result = assess_job_conditions({
        "title": "Paid Frontend internship",
        "description": "Fully remote. Candidates from Russia are eligible. Paid stipend 40,000 RUB.",
        "opportunity_type": "paid_placement",
    })
    assert result["ats_remote_status"] == "confirmed"
    assert result["ats_russia_eligibility"] == "confirmed"
    assert result["ats_paid_status"] == "confirmed"


def test_hybrid_and_unpaid_are_blocked_and_unknown_russia_stays_unknown():
    result = assess_job_conditions({
        "title": "Junior Frontend Developer",
        "description": "Hybrid office schedule. Unpaid internship.",
        "opportunity_type": "paid_placement",
    })
    assert result["ats_remote_status"] == "blocked"
    assert result["ats_russia_eligibility"] == "unknown"
    assert result["ats_paid_status"] == "blocked"


def test_generic_remote_does_not_prove_russia_eligibility():
    result = assess_job_conditions({
        "title": "Remote React Developer",
        "description": "Remote worldwide",
        "work_mode": "remote",
    })
    assert result["ats_remote_status"] == "confirmed"
    assert result["ats_russia_eligibility"] == "unknown"
    assert result["ats_paid_status"] == "not_applicable"
