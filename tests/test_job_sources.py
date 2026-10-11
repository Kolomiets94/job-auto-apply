from unittest.mock import Mock, patch
import job_sources
from profit_ranker import rank_lead
from application_dispatcher import dispatch
from proposal_writer import make_proposal
import pytest


def test_trudvsem_preserves_vacancy_contact_and_remote_requirement():
    remote = {'job-name': 'Junior Frontend React', 'vac_url': 'https://trudvsem.ru/vacancy/card/x/y',
              'duty': 'удалённая работа', 'requirements': 'React TypeScript',
              'contact_list': [{'contact_type': 'Эл. почта', 'contact_value': 'jobs@example.com'}]}
    onsite = {**remote, 'duty': 'работа в офисе'}
    payload = {'results': {'vacancies': [{'vacancy': remote}, {'vacancy': onsite}]}}
    with patch.object(job_sources, 'response', return_value=Mock(json=lambda: payload)):
        leads = job_sources.trudvsem()
    assert len(leads) == 3
    assert all(l['apply_email'] == 'jobs@example.com' for l in leads)
    assert 'React TypeScript' in leads[0]['description']


def test_worldwide_does_not_override_explicit_restriction():
    lead = {'source': 'jobicy', 'title': 'Junior Frontend React', 'location': 'Worldwide',
            'description': 'worldwide company, US only'}
    assert not rank_lead(lead)['eligible']
    lead['description'] = 'React TypeScript remote'
    assert rank_lead(lead)['eligible']
    lead['location'] = 'USA'
    assert not rank_lead(lead)['eligible']


def test_mailto_uses_real_delivery_and_checks_rejection(monkeypatch):
    for k,v in {'AUTO_SEND_EMAIL':'1','SMTP_HOST':'smtp.example.com','SMTP_USER':'alex@example.com','SMTP_PASSWORD':'x'}.items():
        monkeypatch.setenv(k,v)
    lead = {'apply_url': 'mailto:jobs@example.com', 'title': 'Junior Frontend'}
    with patch('application_dispatcher.smtplib.SMTP_SSL') as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        assert dispatch(lead, 'Hello')['status'] == 'SUBMITTED'
        smtp.return_value.__enter__.return_value.send_message.return_value = {'jobs@example.com': (550, b'no')}
        assert dispatch(lead, 'Hello')['status'] == 'FAILED'


def test_international_qa_letter_is_truthful_and_in_english():
    letter = make_proposal({'category':'qa','language':'en','title':'Junior QA','company':'Acme'})
    assert 'Junior QA' in letter
    assert 'manually tested my own React web applications' in letter
    assert 'https://github.com/Kolomiets94/travel-blog' in letter
    assert 'commercial QA experience' not in letter


def test_explicit_apply_email_is_extracted_but_generic_contact_is_not():
    assert job_sources.explicit_application_email(
        '<a href="mailto:jobs@example.org">Apply via email</a>'
    ) == 'jobs@example.org'
    assert job_sources.explicit_application_email(
        '<a href="mailto:privacy@example.org">Privacy inquiries</a>'
    ) is None
    assert job_sources.explicit_application_email(
        'Send your resume to jobs@example.org for this position'
    ) == 'jobs@example.org'
