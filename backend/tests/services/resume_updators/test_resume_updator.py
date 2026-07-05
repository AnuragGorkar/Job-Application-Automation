import pytest
import aiofiles
from pathlib import Path
from app.schemas.resume_schemas import ResumeChanges
from app.services.resume_updators.resume_updator import ResumeUpdator

# Base template mimicking your actual LaTeX file
BASE_LATEX_CONTENT = """
\\begin{document}
% SUM_START
Old summary text.
% SUM_END

% COURSES_1_START
Courses: Old Math
% COURSES_1_END

% EXP_1_B1_START
Old bullet point.
% EXP_1_B1_END

% PROJ_1_TECH_START
Old $|$ Tech
% PROJ_1_TECH_END

% TECHNICAL_SKILLS_START
\\textbf{Old}{: Skills} \\\\
% TECHNICAL_SKILLS_END
\\end{document}
"""

@pytest.fixture
def temp_resume_file(tmp_path: Path) -> str:
    """Creates a temporary LaTeX file for testing file I/O."""
    file_path = tmp_path / "test_resume.tex"
    # Setup synchronously for simplicity
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(BASE_LATEX_CONTENT)
    return str(file_path)

@pytest.fixture
def updater(temp_resume_file: str) -> ResumeUpdator:
    """Returns an updater pointed at the temp file."""
    return ResumeUpdator(temp_resume_file)

# --- Sync Regex Tests ---

def test_replace_tag_content_basic(updater):
    content = "% SUM_START\nold\n% SUM_END"
    new_text = "new summary text"
    
    result = updater._replace_tag_content(content, "SUM", new_text)
    
    assert "new summary text" in result
    assert "old" not in result
    assert "% SUM_START\nnew summary text\n% SUM_END" in result

def test_replace_tag_content_empty_text(updater):
    content = "% SUM_START\nold\n% SUM_END"
    
    result = updater._replace_tag_content(content, "SUM", "")
    
    # Should return original content unmodified
    assert result == content
    assert "old" in result

def test_replace_tag_content_multiline(updater):
    content = "% TECHNICAL_SKILLS_START\nold line\n% TECHNICAL_SKILLS_END"
    new_text = "\\textbf{Lang}{: Py} \\\\\n\\textbf{DB}{: SQL} \\\\"
    
    result = updater._replace_tag_content(content, "TECHNICAL_SKILLS", new_text)
    
    assert "\\textbf{Lang}{: Py} \\\\" in result
    assert "old line" not in result

# --- Async File I/O Tests ---

@pytest.mark.asyncio
async def test_apply_changes_empty(updater, temp_resume_file):
    changes = ResumeChanges() # All None
    
    await updater.apply_changes(changes)
    
    # File should remain unchanged
    with open(temp_resume_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "Old summary text." in content
    assert "Old bullet point." in content

@pytest.mark.asyncio
async def test_apply_changes_summary_only(updater, temp_resume_file):
    changes = ResumeChanges(SUM="Brand new summary.")
    
    await updater.apply_changes(changes)
    
    with open(temp_resume_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "Brand new summary." in content
    assert "Old summary text." not in content
    # Ensure others didn't change
    assert "Old bullet point." in content

@pytest.mark.asyncio
async def test_apply_changes_dictionary_fields(updater, temp_resume_file):
    changes = ResumeChanges(
        COURSES={"COURSES_1": "Courses: New Math"},
        EXP={"EXP_1_B1": "New bullet point."},
        PROJ={"PROJ_1_TECH": "New $|$ Tech"}
    )
    
    await updater.apply_changes(changes)
    
    with open(temp_resume_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Check new values
    assert "Courses: New Math" in content
    assert "New bullet point." in content
    assert "New $|$ Tech" in content
    
    # Check old values removed
    assert "Courses: Old Math" not in content
    assert "Old bullet point." not in content
    assert "Old $|$ Tech" not in content

@pytest.mark.asyncio
async def test_apply_changes_all_fields(updater, temp_resume_file):
    changes = ResumeChanges(
        SUM="New sum.",
        COURSES={"COURSES_1": "Courses: New"},
        EXP={"EXP_1_B1": "New exp."},
        PROJ={"PROJ_1_TECH": "New proj."},
        TECHNICAL_SKILLS="New skills."
    )
    
    await updater.apply_changes(changes)
    
    with open(temp_resume_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "New sum." in content
    assert "Courses: New" in content
    assert "New exp." in content
    assert "New proj." in content
    assert "New skills." in content
    
    assert "Old summary text." not in content