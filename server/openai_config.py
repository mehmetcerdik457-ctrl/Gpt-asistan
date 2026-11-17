"""Server-only credential selection, including the managed proxy binding alias."""
import os


def api_key(environ=None):
    values = os.environ if environ is None else environ
    for name in ("OPENAI_API_KEY", "KRAL_OPENAI_API_KEY"):
        value = values.get(name, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def contains_credential(value, environ=None):
    """Keep either configured credential out of public configuration/evidence fields."""
    values = os.environ if environ is None else environ
    if not isinstance(value, str):
        return False
    for name in ("OPENAI_API_KEY", "KRAL_OPENAI_API_KEY"):
        key = values.get(name, "")
        if isinstance(key, str) and key.strip() and key.strip() in value:
            return True
    return False
