from pydantic import ValidationError
from app.schemas.resume_schemas import ResumeChanges
from app.services.resume_updaters.resume_validator import ResumeValidator
from app.services.resume_updaters.resume_updater import ResumeUpdater
from app.services.resume_updaters.exceptions import ResumeValidationError

class ResumeManager:
    def __init__(self, file_path: str):
        self.updater = ResumeUpdater(file_path)
        self.validator = ResumeValidator()

    async def process_llm_response(self, raw_llm_json: str) -> str:
        """
        Takes raw string from LLM. 
        Returns "SUCCESS" if applied, or an error prompt to send back to LLM.
        """
        try:
            # 1. Convert string to ResumeChanges object
            changes = ResumeChanges.model_validate_json(raw_llm_json)

            # 2. Run strict business validations
            self.validator.validate(changes)

            # 3. Apply to LaTeX file
            await self.updater.apply_changes(changes)

            return "SUCCESS"

        except ValidationError as e:
            # Fails here if LLM returns bad JSON keys or wrong data types
            error_details = []
            for err in e.errors():
                loc = " -> ".join(str(l) for l in err["loc"])
                error_details.append(f"Location [{loc}]: {err['msg']}")
            
            format_err_prompt = "JSON schema error. Fix these structure issues:\n" + "\n".join(error_details)
            return format_err_prompt
            
        except ResumeValidationError as e:
            # Fails here if LaTeX is bad, text too long, or wrong formatting
            return e.to_llm_prompt()
            
        except Exception as e:
            # Fails here if JSON is completely broken/unparsable
            return f"Fatal parse error. Ensure output is ONLY valid JSON. Error: {str(e)}"