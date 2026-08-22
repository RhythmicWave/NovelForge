import importlib, sys
sys.path.insert(0, "/home/luo/projects/NovelForge/backend/.venv/lib/python3.11/site-packages")
mods = ["fastapi", "langchain", "langchain_openai", "sqlmodel", "pydantic", "neo4j", "uvicorn"]
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"OK  {m} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"FAIL {m}: {type(e).__name__}: {e}")
