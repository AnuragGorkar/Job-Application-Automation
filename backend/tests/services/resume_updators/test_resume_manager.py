import pytest
import json
from pathlib import Path
from app.services.resume_updaters.resume_manager import ResumeManager

@pytest.fixture
def temp_resume_file(tmp_path: Path) -> str:
    # Read actual template from test_data
    template_path = Path("tests/test_data/test_resume.tex")
    
    # Create working copy in temp directory
    temp_file = tmp_path / "test_resume_copy.tex"
    temp_file.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
    
    return str(temp_file)

@pytest.fixture
def manager(temp_resume_file: str) -> ResumeManager:
    return ResumeManager(temp_resume_file)


# --- 1. FATAL PARSE ERRORS ---
@pytest.mark.asyncio
async def test_fatal_parse_error(manager, temp_resume_file):
    original_content = Path(temp_resume_file).read_text(encoding="utf-8")
    
    raw_bad_string = "Not JSON. {SUM: hello}"
    result = await manager.process_llm_response(raw_bad_string)
    
    assert result != "SUCCESS"
    assert "Invalid JSON" in result or "JSON schema error" in result
    
    # Ensure file not touched
    current_content = Path(temp_resume_file).read_text(encoding="utf-8")
    assert original_content == current_content


# --- 2. SCHEMA ERRORS ---
@pytest.mark.asyncio
@pytest.mark.parametrize("payload, expected_error", [
    (
        {"SUM": ["Should be string"]}, 
        "valid string"
    ),
    (
        {"COURSES": "Should be dict"}, 
        "object" # Pydantic says "Input should be an object"
    ),
    (
        {"EXP": ["List instead of dict"]}, 
        "object"
    ),
    (
        {"PROJ": {"PROJ_1_TECH": {"nested": "dict"}}}, 
        "valid string"
    ),
])
async def test_schema_errors(manager, temp_resume_file, payload, expected_error):
    original_content = Path(temp_resume_file).read_text(encoding="utf-8")
    
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result != "SUCCESS"
    assert "JSON schema error" in result
    assert expected_error in result
    
    # Ensure file not touched
    current_content = Path(temp_resume_file).read_text(encoding="utf-8")
    assert original_content == current_content


# --- 3. BUSINESS VALIDATION ERRORS ---
@pytest.mark.asyncio
@pytest.mark.parametrize("payload, expected_error_snippet", [
    # Summary
    ({"SUM": "Unescaped % sign"}, "Unescaped LaTeX characters"),
    ({"SUM": "A" * 801}, "exceeds 800 chars"),
    
    # Courses
    ({"COURSES": {"BAD_KEY": "Courses: Math"}}, "Invalid key 'BAD_KEY'"),
    ({"COURSES": {"COURSES_1": "Math and Science"}}, "Must start with 'Courses: '"),
    ({"COURSES": {"COURSES_1": "Courses: Math,"}}, "Cannot end with comma"),
    ({"COURSES": {"COURSES_1": "Courses: A,B"}}, "Commas must be followed by space"),
    ({"COURSES": {"COURSES_1": "Courses: A, B, C, D, E"}}, "Max 4 courses"),
    
    # Experience
    ({"EXP": {"EXP_99": "Bad key"}}, "Invalid key 'EXP_99'"),
    ({"EXP": {"EXP_1_B1": "Ended with dot."}}, "Cannot end with comma or full stop"),
    ({"EXP": {"EXP_1_B1": "Unescaped & symbol"}}, "Unescaped LaTeX"),
    ({"EXP": {"EXP_1_B1": "X" * 401}}, "exceeds 400 chars"),
    
    # Projects
    ({"PROJ": {"BAD_PROJ": "Desc"}}, "Invalid key 'BAD_PROJ'"),
    ({"PROJ": {"PROJ_1_TECH": "Python | Java"}}, "Use '$|$' separator"),
    ({"PROJ": {"PROJ_1_TECH": "Python$|$Java"}}, "Must have space before and after"),
    ({"PROJ": {"PROJ_1_TECH": "A $|$ B $|$ C $|$ D $|$ E $|$ F"}}, "Max 5 technologies"),
    ({"PROJ": {"PROJ_1_DESC": "Description with %"}}, "Unescaped LaTeX"),
    ({"PROJ": {"PROJ_1_DESC": "Ends with dot."}}, "Cannot end with comma or full stop"),
])
async def test_validation_errors_general(manager, temp_resume_file, payload, expected_error_snippet):
    original_content = Path(temp_resume_file).read_text(encoding="utf-8")
    
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result != "SUCCESS"
    assert expected_error_snippet in result
    
    # Ensure file not touched
    current_content = Path(temp_resume_file).read_text(encoding="utf-8")
    assert original_content == current_content


# --- 4. EXHAUSTIVE TECHNICAL SKILLS VALIDATION ---
@pytest.mark.asyncio
@pytest.mark.parametrize("skills_text, expected_error_snippet", [
    ("Languages: Python \\\\", "format broken"),
    ("\\textbf{Languages}{: Python}", "must end with ' \\\\'"),
    ("\\textbf{Languages}{: Python %} \\\\", "Unescaped LaTeX"),
    ("\\textbf{L}{: Python} \\\\\n" * 5, "Max 4 skill lines"),
    ("\\textbf{L}{: " + ("x" * 150) + "} \\\\", "exceeds 150 chars"),
    ("\\textbf{Languages}{: Python,Java} \\\\", "Commas must be followed by space"),
])
async def test_validation_errors_technical_skills(manager, skills_text, expected_error_snippet):
    payload = {"TECHNICAL_SKILLS": skills_text}
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result != "SUCCESS"
    assert expected_error_snippet in result


# --- 5. MULTIPLE ERRORS ACCUMULATION ---
@pytest.mark.asyncio
async def test_multiple_errors_returned(manager):
    payload = {
        "SUM": "Unescaped $",
        "COURSES": {"COURSES_1": "Missing prefix"},
        "PROJ": {"PROJ_1_TECH": "Bad | separator"}
    }
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result != "SUCCESS"
    assert "Unescaped LaTeX characters" in result
    assert "Must start with 'Courses: '" in result
    assert "Use '$|$' separator" in result


# --- 6. SUCCESSFUL FILE UPDATES ---
@pytest.mark.asyncio
async def test_successful_partial_update(manager, temp_resume_file):
    # Update only one section. Others should remain untouched.
    payload = {"SUM": "New summary without special chars"}
    
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result == "SUCCESS"
    
    content = Path(temp_resume_file).read_text(encoding="utf-8")
    assert "New summary without special chars" in content
    
    # Verify standard LaTeX structural text is untouched
    assert "EDUCATION" in content
    assert "Anurag Gorkar" in content


@pytest.mark.asyncio
async def test_successful_full_update(manager, temp_resume_file):
    payload = {
        "SUM": "Brand new summary",
        "COURSES": {
            "COURSES_1": "Courses: New Math, New Science"
        },
        "EXP": {
            "EXP_1_B1": "Replaced first bullet"
        },
        "PROJ": {
            "PROJ_1_TECH": "Go $|$ Python"
        },
        "TECHNICAL_SKILLS": "\\textbf{New Category}{: Valid Skill} \\\\"
    }
    
    llm_json = json.dumps(payload)
    result = await manager.process_llm_response(llm_json)
    
    assert result == "SUCCESS"
    
    content = Path(temp_resume_file).read_text(encoding="utf-8")
    
    assert "Brand new summary" in content
    assert "Courses: New Math, New Science" in content
    assert "Replaced first bullet" in content
    assert "Go $|$ Python" in content
    assert "\\textbf{New Category}{: Valid Skill} \\\\" in content