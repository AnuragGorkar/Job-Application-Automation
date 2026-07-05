import re
from typing import List
from app.schemas.resume_schemas import ResumeChanges, ResumeError
from app.services.resume_updaters.exceptions import ResumeValidationError
from app.services.resume_updaters.validation_error_enum import ResumeErrorType
from app.services.resume_updaters.resume_section_enum import ResumeSectionType
from app.services.resume_updaters import resume_constants as const

class ResumeValidator:
    
    def __init__(self):
        self.errors: List[ResumeError] = []
        self.changes: ResumeChanges = None

    def _check_latex_safety(self, text: str, section: ResumeSectionType) -> None:
        unescaped_pattern = re.compile(r'(?<!\\)[$%&#_]')
        if unescaped_pattern.search(text):
            self.errors.append(ResumeError(
                error=ResumeErrorType.INVALID_LATEX,
                message="Unescaped LaTeX characters found. Escape $, %, &, #, _ with backslash (\\).",
                section=section
            ))

    def _check_comma_spacing(self, text: str, section: ResumeSectionType) -> None:
        # (?!$) prevents matching commas at the very end of the string
        if re.search(r',(?!\s)(?!$)', text):
            self.errors.append(ResumeError(
                error=ResumeErrorType.INVALID_FORMAT,
                message="Commas must be followed by space.",
                section=section
            ))

    def _validate_summary(self) -> None:
        text = self.changes.SUM
        if not text:
            return
            
        if len(text) > const.SUMMARY_MAX_LEN:
            self.errors.append(ResumeError(
                error=ResumeErrorType.TEXT_TOO_LONG,
                message=f"Summary exceeds {const.SUMMARY_MAX_LEN} chars.",
                section=ResumeSectionType.SUMMARY
            ))
            
        self._check_latex_safety(text, ResumeSectionType.SUMMARY)

    def _validate_courses(self) -> None:
        courses = self.changes.COURSES
        if not courses:
            return
            
        for key, text in courses.items():
            if key not in const.ALLOWED_COURSES_KEYS:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message=f"Invalid key '{key}'.",
                    section=ResumeSectionType.COURSES
                ))
                continue
            
            if not text.startswith("Courses: "):
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message="Must start with 'Courses: '.",
                    section=ResumeSectionType.COURSES
                ))
                
            if text.endswith(",") or text.endswith("."):
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message="Cannot end with comma or full stop.",
                    section=ResumeSectionType.COURSES
                ))
                
            course_list = text.replace("Courses: ", "").split(",")
            if len(course_list) > 4:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message="Max 4 courses allowed.",
                    section=ResumeSectionType.COURSES
                ))

            self._check_comma_spacing(text, ResumeSectionType.COURSES)
            self._check_latex_safety(text, ResumeSectionType.COURSES)

    def _validate_experience(self) -> None:
        exp = self.changes.EXP
        if not exp:
            return
            
        for key, text in exp.items():
            if key not in const.ALLOWED_EXP_KEYS:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message=f"Invalid key '{key}'.",
                    section=ResumeSectionType.EXPERIENCE
                ))
                continue
                
            if len(text) > const.EXP_MAX_LEN:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.TEXT_TOO_LONG,
                    message=f"Bullet {key} exceeds {const.EXP_MAX_LEN} chars.",
                    section=ResumeSectionType.EXPERIENCE
                ))

            if text.strip().endswith("."):
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message="Experience bullet cannot end with full stop.",
                    section=ResumeSectionType.EXPERIENCE
                ))
                
            self._check_comma_spacing(text, ResumeSectionType.EXPERIENCE)
            self._check_latex_safety(text, ResumeSectionType.EXPERIENCE)

    def _validate_projects(self) -> None:
        proj = self.changes.PROJ
        if not proj:
            return
            
        for key, text in proj.items():
            if key not in const.ALLOWED_PROJ_KEYS:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message=f"Invalid key '{key}'.",
                    section=ResumeSectionType.PROJECTS
                ))
                continue

            if len(text) > const.PROJ_MAX_LEN:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.TEXT_TOO_LONG,
                    message=f"Project item {key} exceeds {const.PROJ_MAX_LEN} chars.",
                    section=ResumeSectionType.PROJECTS
                ))

            if "TECH" in key:
                if re.search(r'(?<!\$)\|(?!\$)', text):
                    self.errors.append(ResumeError(
                        error=ResumeErrorType.INVALID_FORMAT,
                        message="Use '$|$' separator, not standard '|'.",
                        section=ResumeSectionType.PROJECTS
                    ))
                
                if re.search(r'(?<!\s)\$\|\$', text) or re.search(r'\$\|\$(?!\s)', text):
                    self.errors.append(ResumeError(
                        error=ResumeErrorType.INVALID_FORMAT,
                        message="Must have space before and after '$|$'.",
                        section=ResumeSectionType.PROJECTS
                    ))

                tech_count = len(text.split("$|$"))
                if tech_count > 5:
                    self.errors.append(ResumeError(
                        error=ResumeErrorType.INVALID_FORMAT,
                        message="Max 5 technologies allowed.",
                        section=ResumeSectionType.PROJECTS
                    ))

                # Strip $|$ before checking latex to avoid false positive on $
                latex_check_text = text.replace("$|$", "")
            else:
                latex_check_text = text

            self._check_comma_spacing(text, ResumeSectionType.PROJECTS)
            self._check_latex_safety(latex_check_text, ResumeSectionType.PROJECTS)

    def _validate_technical_skills(self) -> None:
        skills = self.changes.TECHNICAL_SKILLS
        if not skills:
            return
            
        lines = [line.strip() for line in skills.split('\n') if line.strip()]
        
        if len(lines) > const.SKILLS_MAX_LINES:
            self.errors.append(ResumeError(
                error=ResumeErrorType.TEXT_TOO_LONG,
                message=f"Max {const.SKILLS_MAX_LINES} skill lines. Found {len(lines)}.",
                section=ResumeSectionType.SKILLS
            ))
            
        line_pattern = re.compile(r'^\\textbf\{[^}]+\}\{[^}]+\}(\s*\\\\)?$')
        
        for index, line in enumerate(lines):
            if len(line) > const.SKILLS_LINE_MAX_LEN:
                self.errors.append(ResumeError(
                    error=ResumeErrorType.TEXT_TOO_LONG,
                    message=f"Skill line {index + 1} exceeds {const.SKILLS_LINE_MAX_LEN} chars.",
                    section=ResumeSectionType.SKILLS
                ))
                
            if not line_pattern.match(line):
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message=f"Line {index + 1} format broken. Must match: \\textbf{{Category}}{{: Skill1}} \\\\",
                    section=ResumeSectionType.SKILLS
                ))
            
            if index < len(lines) - 1 and not line.endswith(r'\\'):
                self.errors.append(ResumeError(
                    error=ResumeErrorType.INVALID_FORMAT,
                    message=f"Line {index + 1} must end with ' \\\\'.",
                    section=ResumeSectionType.SKILLS
                ))

            self._check_latex_safety(line, ResumeSectionType.SKILLS)

    def validate(self, changes: ResumeChanges) -> bool:
        self.changes = changes
        self.errors.clear() 

        self._validate_summary()
        self._validate_courses()
        self._validate_experience()
        self._validate_projects()
        self._validate_technical_skills()

        if self.errors:
            raise ResumeValidationError(self.errors)

        return True