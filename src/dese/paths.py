from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "templates"
SCHEMA_DIR = BASE_DIR / "schemas"

DEFAULT_TEMPLATE_PATH = TEMPLATE_DIR / "empty_model.json"
DEFAULT_SCHEMA_PATH = SCHEMA_DIR / "schema.json"
