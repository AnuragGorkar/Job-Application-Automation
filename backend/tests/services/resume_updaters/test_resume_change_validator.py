import pytest
from app.schemas.resume_schemas import ResumeChanges
from app.services.resume_updaters.resume_validator import ResumeValidator
from app.services.resume_updaters.validation_error_enum import ResumeErrorType
from app.services.resume_updaters.resume_section_enum import ResumeSectionType
from app.services.resume_updaters import resume_constants as const

@pytest.fixture
def validator():
    return ResumeValidator()

# --- 1. _check_latex_safety ---
@pytest.mark.parametrize("text, expected_errors", [
    ("Safe text without special chars", 0),
    ("Escaped \\$, \\%, \\&, \\#, \\_ are fine", 0),
    ("Unescaped $ breaks it", 1),
    ("Unescaped % breaks it", 1),
    ("Unescaped & breaks it", 1),
    ("Unescaped # breaks it", 1),
    ("Unescaped _ breaks it", 1),
    ("Mixed valid \\$ and invalid %", 1),
])
def test_check_latex_safety(validator, text, expected_errors):
    validator.changes = ResumeChanges()
    validator._check_latex_safety(text, ResumeSectionType.SUMMARY)
    assert len(validator.errors) == expected_errors
    if expected_errors > 0:
        assert validator.errors[0].error == ResumeErrorType.INVALID_LATEX

# --- 2. _check_comma_spacing ---
@pytest.mark.parametrize("text, expected_errors", [
    ("Valid text, with space", 0),
    ("Invalid text,without space", 1),
    ("Multiple, bad,commas", 1),
    ("Ending comma does not trigger this regex,", 0), 
])
def test_check_comma_spacing(validator, text, expected_errors):
    validator.changes = ResumeChanges()
    validator._check_comma_spacing(text, ResumeSectionType.SUMMARY)
    assert len(validator.errors) == expected_errors
    if expected_errors > 0:
        assert validator.errors[0].error == ResumeErrorType.INVALID_FORMAT

# --- 3. _validate_summary ---
@pytest.mark.parametrize("summary, expected_error_types", [
    (None, []),
    ("Normal summary text.", []),
    ("x" * (const.SUMMARY_MAX_LEN + 1), [ResumeErrorType.TEXT_TOO_LONG]),
    ("Summary with unescaped $", [ResumeErrorType.INVALID_LATEX]),
    ("x" * (const.SUMMARY_MAX_LEN + 1) + "$", [ResumeErrorType.TEXT_TOO_LONG, ResumeErrorType.INVALID_LATEX]),
])
def test_validate_summary(validator, summary, expected_error_types):
    validator.changes = ResumeChanges(SUM=summary)
    validator._validate_summary()
    assert len(validator.errors) == len(expected_error_types)
    for err, expected_type in zip(validator.errors, expected_error_types):
        assert err.error == expected_type

# --- 4. _validate_courses ---
@pytest.mark.parametrize("courses, expected_error_types", [
    (None, []),
    ({"COURSES_1": "Courses: Math, Science"}, []),
    ({"INVALID_KEY": "Courses: Math"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Math, Science"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Courses: Math,"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Courses: Math."}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Courses: A, B, C, D, E"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Courses: Math,Science"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"COURSES_1": "Courses: Math $"}, [ResumeErrorType.INVALID_LATEX]),
])
def test_validate_courses(validator, courses, expected_error_types):
    validator.changes = ResumeChanges(COURSES=courses)
    validator._validate_courses()
    assert len(validator.errors) == len(expected_error_types)
    for err, expected_type in zip(validator.errors, expected_error_types):
        assert err.error == expected_type

# --- 5. _validate_experience ---
@pytest.mark.parametrize("exp, expected_error_types", [
    (None, []),
    ({"EXP_1_B1": "Built a great backend framework"}, []),
    ({"INVALID_EXP_KEY": "Text"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"EXP_1_B1": "x" * (const.EXP_MAX_LEN + 1)}, [ResumeErrorType.TEXT_TOO_LONG]),
    ({"EXP_1_B1": "Ended with a full stop."}, [ResumeErrorType.INVALID_FORMAT]),
    ({"EXP_1_B1": "Unescaped % sign"}, [ResumeErrorType.INVALID_LATEX]),
])
def test_validate_experience(validator, exp, expected_error_types):
    validator.changes = ResumeChanges(EXP=exp)
    validator._validate_experience()
    assert len(validator.errors) == len(expected_error_types)
    for err, expected_type in zip(validator.errors, expected_error_types):
        assert err.error == expected_type

# --- 6. _validate_projects ---
@pytest.mark.parametrize("proj, expected_error_types", [
    (None, []),
    ({"PROJ_1_DESC": "Normal description"}, []),
    ({"PROJ_1_TECH": "Python $|$ Java"}, []),
    ({"INVALID_PROJ_KEY": "Text"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"PROJ_1_DESC": "x" * (const.PROJ_MAX_LEN + 1)}, [ResumeErrorType.TEXT_TOO_LONG]),
    ({"PROJ_1_TECH": "Python | Java"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"PROJ_1_TECH": "Python$|$Java"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"PROJ_1_TECH": "A $|$ B $|$ C $|$ D $|$ E $|$ F"}, [ResumeErrorType.INVALID_FORMAT]),
    ({"PROJ_1_TECH": "Python $|$ Java $"}, [ResumeErrorType.INVALID_LATEX]),
])
def test_validate_projects(validator, proj, expected_error_types):
    validator.changes = ResumeChanges(PROJ=proj)
    validator._validate_projects()
    assert len(validator.errors) == len(expected_error_types)
    for err, expected_type in zip(validator.errors, expected_error_types):
        assert err.error == expected_type

# --- 7. _validate_technical_skills ---
@pytest.mark.parametrize("skills, expected_error_types", [
    (None, []),
    ("\\textbf{Languages}{: Python} \\\\", []),
    ("\\textbf{Languages}{: Python} \\\\\n\\textbf{Tools}{: Git} \\\\", []),
    ("\\textbf{L}{: A} \\\\\n" * 5, [ResumeErrorType.TEXT_TOO_LONG]),
    # Regex matches format, but string is too long. Only 1 error.
    (f"\\textbf{{L}}{{{'x' * const.SKILLS_LINE_MAX_LEN}}} \\\\", [ResumeErrorType.TEXT_TOO_LONG]),
    ("Languages: Python \\\\", [ResumeErrorType.INVALID_FORMAT]),
    ("\\textbf{Languages}{: Python}\n\\textbf{Tools}{: Git} \\\\", [ResumeErrorType.INVALID_FORMAT]),
    ("\\textbf{Tools}{: Git, %} \\\\", [ResumeErrorType.INVALID_LATEX]),
])
def test_validate_technical_skills(validator, skills, expected_error_types):
    validator.changes = ResumeChanges(TECHNICAL_SKILLS=skills)
    validator._validate_technical_skills()
    assert len(validator.errors) == len(expected_error_types)
    for err, expected_type in zip(validator.errors, expected_error_types):
        assert err.error == expected_type