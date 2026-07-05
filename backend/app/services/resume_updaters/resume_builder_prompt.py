from app.services.resume_updaters import resume_constants as const

class ResumePromptBuilder:
    
    def get_format_instructions(self) -> str:
        return f"""
OUTPUT FORMAT REQUIREMENT:
You must return ONLY a single JSON object. No markdown, no explanations. 
The JSON represents changes to a LaTeX resume. The backend replaces text between specific LaTeX comments (e.g., % SUM_START and % SUM_END).
You donot include the <> they are just in this example to indicate where the text should live.

JSON STRUCTURE:
{{
  "SUM": "<summary_text>",
  "COURSES": {{
    "COURSES_1": "<course1_text>",
    "COURSES_2": "<course2_text>"
  }},
  "EXP": {{
    "EXP_1_B1": "<bullet_text>",
    "EXP_1_B2": "<bullet_text>"
  }},
  "PROJ": {{
    "PROJ_1_TECH": "<tech_stack>",
    "PROJ_1_DESC": "<description>"
  }},
  "TECHNICAL_SKILLS": "<multiline_skills_text>"
}}

STRICT RULES:
1. Valid JSON only. Escape double quotes inside strings.
2. LaTeX Safety: Escape special characters ($, %, &, #, _) with a backslash (\\).
3. Spacing: All commas must be followed by a space. No commas or full stops at the end of COURSE lines.
4. Missing fields: Omit keys if no changes are needed for that section. Do not send null.

SECTION LIMITS & CONSTRAINTS:

- SUMMARY (SUM):
  Max length: {const.SUMMARY_MAX_LEN} chars.

- COURSES:
  Allowed keys: {', '.join(const.ALLOWED_COURSES_KEYS)}.
  Max length per course: {const.COURSES_MAX_LEN} chars.
  Must start exactly with "Courses: ".

- EXPERIENCE (EXP):
  Allowed keys: {', '.join(const.ALLOWED_EXP_KEYS)}.
  Max length per bullet: {const.EXP_MAX_LEN} chars.

- PROJECTS (PROJ):
  Allowed keys: {', '.join(const.ALLOWED_PROJ_KEYS)}.
  Max length per item: {const.PROJ_MAX_LEN} chars.
  TECH stack lines MUST use `$|$` as the separator (e.g., Python $|$ React $|$ SQL).

- TECHNICAL_SKILLS:
  Max lines: {const.SKILLS_MAX_LINES}.
  Max length per line: {const.SKILLS_LINE_MAX_LEN} chars.
  FORMAT IS STRICT. Each line must exactly match this structure:
  \\textbf{{Category}}{{: Skill1, Skill2, Skill3}} \\\\
  
  Example TECHNICAL_SKILLS value:
  "\\textbf{{Languages}}{{: Python, Java, SQL}} \\\\\\n\\textbf{{Backend}}{{: FastAPI, Postgres}} \\\\"
"""