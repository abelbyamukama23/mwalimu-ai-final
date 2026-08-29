"""Dependency and import smoke tests for the Agent Service foundation."""

import fastapi
import httpx
import openai
import pydantic
import uvicorn

from agent_service.context import ExecutionContext  # noqa: F401
from agent_service.run import AgentRun  # noqa: F401


def test_python_version() -> None:
    """Python 3.13+ is supported."""
    import sys

    assert sys.version_info[:2] in ((3, 13), (3, 14))



def test_fastapi_import() -> None:
    """FastAPI is importable."""
    assert fastapi.__version__ is not None


def test_uvicorn_import() -> None:
    """Uvicorn is importable."""
    assert uvicorn.__version__ is not None


def test_openai_import() -> None:
    """OpenAI SDK is importable."""
    assert openai.__version__ is not None


def test_httpx_import() -> None:
    """HTTPX is importable."""
    assert httpx.__version__ is not None


def test_pydantic_import() -> None:
    """Pydantic v2 is importable."""
    assert pydantic.VERSION.startswith("2.")
