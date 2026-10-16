import pytest


@pytest.fixture(autouse=True)
def isolated_data_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("RAG_DATA_DIR", str(tmp_path / "data"))
