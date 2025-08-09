from sqlmodel import create_engine, Session
from pathlib import Path

# 计算数据库绝对路径，定位到 backend 目录下的 aiauthor.db
BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_FILE = BACKEND_DIR / 'aiauthor.db'
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