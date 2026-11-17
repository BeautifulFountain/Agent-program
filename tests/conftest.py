import os

os.environ["DATABASE_PATH"] = "test_agentflow.db"
os.environ["LLM_MOCK"] = "true"
# Unit and integration tests must be deterministic and must never depend on
# public APIs. External retrieval is covered with isolated collaborators.
os.environ["EXTERNAL_SEARCH_ENABLED"] = "false"

