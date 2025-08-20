from sqlmodel import create_engine, Session
from pathlib import Path
import os, sys

# 数据库路径策略：
# 1) 打包(onefile/onedir)：优先放在可执行文件同目录
# 2) 开发态：放在源码 backend 目录
# 3) 支持通过环境变量 AIAUTHOR_DB_PATH 覆盖绝对路径
if getattr(sys, "frozen", False):
	base_dir = Path(sys.executable).resolve().parent
else:
	base_dir = Path(__file__).resolve().parents[2]

DB_FILE = Path(os.getenv("AIAUTHOR_DB_PATH", (base_dir / 'aiauthor.db').as_posix()))
DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"

# 创建数据库引擎（SQLite 需要此参数以允许多线程访问）
engine = create_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})


def get_session():
    """
    FastAPI dependency that provides a transactional database session.
    It ensures that the session is committed on success and rolled back on error.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close() 