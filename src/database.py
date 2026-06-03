"""数据库配置"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

# 数据库配置 - 使用 postgres 数据库
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123456@localhost:5432/postgres"
)

# 创建引擎，使用NullPool避免连接池的编码问题
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # 禁用连接池，每次创建新连接
    echo=False,  # 生产环境设为False，调试时设为True
)

# 在连接创建后设置客户端编码为UTF8
@event.listens_for(engine, "connect")
def set_client_encoding(dbapi_connection, connection_record):
    """设置PostgreSQL客户端编码为UTF8"""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET CLIENT_ENCODING TO 'UTF8'")
    cursor.close()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

# 依赖项：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()