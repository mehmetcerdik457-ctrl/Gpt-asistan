"""Server-only OpenAI authentication and project configuration."""
import os
import re


class ProjectConfigurationError(ValueError):
    pass


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


def project_headers(environ=None):
    """Optionally select the same OpenAI project for catalog and model requests."""
    values = os.environ if environ is None else environ
    project = values.get("OPENAI_PROJECT_ID", "")
    if isinstance(project, str):
        project = project.strip()
        if not project:
            return {}
        if re.fullmatch(r"proj_[A-Za-z0-9_-]{1,128}", project) and not contains_credential(project, values):
            return {"OpenAI-Project": project}
    raise ProjectConfigurationError("OPENAI_PROJECT_CONFIGURATION_INVALID")
