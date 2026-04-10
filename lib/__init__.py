# AI Anime Generator Library
# Shared Python library for API integrations and project management.

# Initialize the environment first (.venv activation, .env loading).
from .data_validator import DataValidator, ValidationResult, validate_episode, validate_project
from .env_init import PROJECT_ROOT
from .project_manager import ProjectManager

__all__ = [
    "ProjectManager",
    "PROJECT_ROOT",
    "DataValidator",
    "validate_project",
    "validate_episode",
    "ValidationResult",
]
