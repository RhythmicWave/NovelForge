from sqlmodel import create_engine, Session
from app.core.config import settings

# 从配置获取数据库URL
DATABASE_URL = settings.database.get_database_url()

# 创建数据库引擎（SQLite 需要此参数以允许多线程访问）
engine = create_engine(
    DATABASE_URL,
    echo=settings.database.echo,
    connect_args={"check_same_thread": False}
)


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