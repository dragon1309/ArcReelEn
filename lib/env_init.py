"""Environment initialization helpers.

Loads the project's .env file.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_environment():
    """
    Initialize the project environment.

    1. Locate the project root directory.
    2. Load the .env file.
    """
    # The project root is the parent directory of lib/.
    lib_dir = Path(__file__).parent
    project_root = lib_dir.parent

    # Load the .env file.
    try:
        from dotenv import load_dotenv

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()
    except ImportError:
        pass  # Skip when python-dotenv is not installed.

    return project_root


# Initialize automatically on module import.
PROJECT_ROOT = init_environment()
