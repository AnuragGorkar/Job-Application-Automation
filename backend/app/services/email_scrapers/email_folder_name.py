from enum import Enum

class EmailFolderName(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"