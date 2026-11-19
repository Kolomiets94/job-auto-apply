import pytest

from resume_parser import ResumeParseError, extract_resume_text


def test_extracts_utf8_text_resume(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("Junior JavaScript Developer\nУчебный курс и личные проекты.", encoding="utf-8")
    assert "JavaScript" in extract_resume_text(path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_resume_text(tmp_path / "missing.pdf")


def test_unsupported_format_is_rejected(tmp_path):
    path = tmp_path / "resume.rtf"
    path.write_text("Some sufficiently long resume content.", encoding="utf-8")
    with pytest.raises(ResumeParseError, match="не поддерживается"):
        extract_resume_text(path)


def test_empty_or_too_short_resume_is_rejected(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("short", encoding="utf-8")
    with pytest.raises(ResumeParseError, match="недостаточно"):
        extract_resume_text(path)
