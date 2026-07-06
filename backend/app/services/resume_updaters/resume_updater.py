import aiofiles
import re
from app.schemas.resume_schemas import ResumeChanges

class ResumeUpdater:
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def _replace_tag_content(self, content: str, tag: str, new_text: str) -> str:
        if not new_text:
            return content
        
        tag_str = tag.value if hasattr(tag, 'value') else str(tag)
        
        # Resilient regex:
        # .*? handles any trailing spaces/garbage on the START line
        # (?:\r?\n|\Z) handles Windows/Linux newlines or End-Of-File safely
        pattern = rf'(%\s*{re.escape(tag_str)}_START.*?(?:\r?\n|\Z))(.*?)(%\s*{re.escape(tag_str)}_END)'
        
        return re.sub(
            pattern, 
            lambda m: f"{m.group(1)}{new_text}\n{m.group(3)}", 
            content, 
            flags=re.DOTALL
        )

    async def apply_changes(self, changes: ResumeChanges):
        async with aiofiles.open(self.file_path, mode='r', encoding='utf-8') as f:
            content = await f.read()

        if changes.SUM:
            content = self._replace_tag_content(content, "SUM", changes.SUM)
            
        if changes.TECHNICAL_SKILLS:
            content = self._replace_tag_content(content, "TECHNICAL_SKILLS", changes.TECHNICAL_SKILLS)

        if changes.COURSES:
            for key, text in changes.COURSES.items():
                content = self._replace_tag_content(content, key, text)
                
        if changes.EXP:
            for key, text in changes.EXP.items():
                content = self._replace_tag_content(content, key, text)
                
        if changes.PROJ:
            for key, text in changes.PROJ.items():
                content = self._replace_tag_content(content, key, text)

        async with aiofiles.open(self.file_path, mode='w', encoding='utf-8') as f:
            await f.write(content)