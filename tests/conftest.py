import os
import tempfile

test_directory = tempfile.TemporaryDirectory(prefix="food-ai-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{test_directory.name}/test.db"