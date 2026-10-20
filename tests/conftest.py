import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # make `import rag` work from any cwd

from tests.helpers import build_kb, build_retriever  # noqa: E402


@pytest.fixture(scope="session")
def kb(tmp_path_factory):
    """(settings, retriever) over the synthetic guideline PDFs, built once per test session."""
    root = tmp_path_factory.mktemp("kb")
    settings = build_kb(root)
    return settings, build_retriever(settings)


@pytest.fixture()
def retriever(kb):
    return kb[1]
