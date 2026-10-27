import os
import tempfile

# Keep test writes out of the real h_mem.db (must run before agent.engine_h_mem is imported)
os.environ["H_MEM_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="hmem_test_"), "h_mem_test.db")
# Force offline mode so tests never call the remote APIs
os.environ["METERLESS_RUNTIME_TOKEN"] = ""
os.environ["ZETARIS_API_KEY"] = ""
