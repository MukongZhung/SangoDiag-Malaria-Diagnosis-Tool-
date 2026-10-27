"""Malaria Agent Package"""

import os


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from the project .env without overriding real environment variables."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            # Ignore the placeholders copied from .env.example
            if value.startswith("your_") and value.endswith("_here"):
                continue
            os.environ.setdefault(key.strip(), value)


_load_dotenv()
