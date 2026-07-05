from typing import List
from app.schemas.resume_schemas import ResumeError

class ResumeValidationError(Exception):
    def __init__(self, errors: List[ResumeError]):
        self.errors = errors
        super().__init__("Multiple validation errors found.")

    def to_llm_prompt(self) -> str:
        lines = ["Fix following errors. Return valid JSON:"]
        for err in self.errors:
            lines.append(f"- [{err.section.value}] {err.error.value}: {err.message}")
        return "\n".join(lines)