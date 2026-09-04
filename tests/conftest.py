from pathlib import Path


# pytest.ini keeps all disposable test files under the ignored workspace cache.
(Path(__file__).resolve().parent.parent / ".tmp").mkdir(exist_ok=True)
