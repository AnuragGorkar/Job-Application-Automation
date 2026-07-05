import aiofiles
import re
from app.schemas.resume_schemas import ResumeChanges
from backend.app.services.resume_updaters.resume_section_enum import ResumeSectionType

class ResumeUpdater:
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def _replace_tag_content(self, content: str, tag: str, new_text: str) -> str:
        if not new_text:
            return content
        
        pattern = rf'(%\s*{tag}_START\s*\n)(.*?)(%\s*{tag}_END)'
        return re.sub(pattern, rf'\1{new_text}\n\3', content, flags=re.DOTALL)

    async def apply_changes(self, changes: ResumeChanges):
        async with aiofiles.open(self.file_path, mode='r') as f:
            content = await f.read()

        if changes.SUM:
            content = self._replace_tag_content(content, ResumeSectionType.SUMMARY, changes.SUM)
            
        if changes.TECHNICAL_SKILLS:
            content = self._replace_tag_content(content, ResumeSectionType.SKILLS, changes.TECHNICAL_SKILLS)

        if changes.COURSES:
            for key, text in changes.COURSES.items():
                content = self._replace_tag_content(content, key, text)
                
        if changes.EXP:
            for key, text in changes.EXP.items():
                content = self._replace_tag_content(content, key, text)
                
        if changes.PROJ:
            for key, text in changes.PROJ.items():
                content = self._replace_tag_content(content, key, text)

        async with aiofiles.open(self.file_path, mode='w') as f:
            await f.write(content)