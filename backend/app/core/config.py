"""应用配置管理

统一管理所有配置项，支持环境变量和默认值。
"""

import os
import sys
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class DatabaseSettings(BaseSettings):
    """数据库配置"""
    
    # 数据库路径
    db_path: Optional[str] = Field(default=None, alias="AIAUTHOR_DB_PATH")
    
    # 是否打印SQL日志
    echo: bool = Field(default=False, alias="DB_ECHO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段
    
    def get_database_url(self) -> str:
        """获取数据库URL
        
        策略：
        1) 打包(onefile/onedir)：优先放在可执行文件同目录
        2) 开发态：放在源码 backend 目录
        3) 支持通过环境变量 AIAUTHOR_DB_PATH 覆盖绝对路径
        
        Returns:
            数据库URL
        """
        if self.db_path:
            db_file = Path(self.db_path)
        else:
            if getattr(sys, "frozen", False):
                base_dir = Path(sys.executable).resolve().parent
            else:
                # 从 app/core/config.py 向上2层到 backend/
                # config.py -> core/ -> app/ -> backend/
                base_dir = Path(__file__).resolve().parents[2]
            db_file = base_dir / 'aiauthor.db'
        
        return f"sqlite:///{db_file.as_posix()}"


class KnowledgeGraphSettings(BaseSettings):
    """知识图谱配置"""
    
    # 知识图谱Provider
    provider: str = Field(default="neo4j", alias="KNOWLEDGE_GRAPH_PROVIDER")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段


class Neo4jSettings(BaseSettings):
    """Neo4j图数据库配置"""
    
    uri: str = Field(default="neo4j://127.0.0.1:7687", alias="NEO4J_URI")
    user: str = Field(default="neo4j", alias="NEO4J_USER")
    password: str = Field(default="neo4j", alias="NEO4J_PASSWORD")
    
    # 兼容旧环境变量
    graph_db_uri: Optional[str] = Field(default=None, alias="GRAPH_DB_URI")
    graph_db_user: Optional[str] = Field(default=None, alias="GRAPH_DB_USER")
    graph_db_password: Optional[str] = Field(default=None, alias="GRAPH_DB_PASSWORD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段
    
    def get_uri(self) -> str:
        """获取URI（兼容旧环境变量）"""
        return self.graph_db_uri or self.uri
    
    def get_user(self) -> str:
        """获取用户名（兼容旧环境变量）"""
        return self.graph_db_user or self.user
    
    def get_password(self) -> str:
        """获取密码（兼容旧环境变量）"""
        return self.graph_db_password or self.password


class BootstrapSettings(BaseSettings):
    """启动初始化配置"""
    
    # 是否覆盖更新内置数据（提示词、知识库等）
    overwrite: bool = Field(default=True, alias="BOOTSTRAP_OVERWRITE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段
    
    @property
    def should_overwrite(self) -> bool:
        """是否应该覆盖更新
        
        支持多种格式：true/false, 1/0, yes/no, on/off
        
        Returns:
            是否覆盖
        """
        if isinstance(self.overwrite, bool):
            return self.overwrite
        return str(self.overwrite).lower() in ('1', 'true', 'yes', 'on')


class AISettings(BaseSettings):
    """AI相关配置"""
    
    # 模型调用失败时最大重试次数
    max_tool_call_retries: int = Field(default=3, alias="MAX_TOOL_CALL_RETRIES")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段


class AppSettings(BaseSettings):
    """应用配置"""
    
    # 应用名称
    app_name: str = Field(default="NovelForge", alias="APP_NAME")
    
    # 应用版本
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    
    # 是否开启调试模式
    debug: bool = Field(default=False, alias="DEBUG")
    
    # API前缀
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    
    # CORS允许的源
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略额外字段
    
    def get_cors_origins_list(self) -> list:
        """获取CORS源列表
        
        Returns:
            源列表
        """
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


class Settings:
    """全局配置对象"""
    
    def __init__(self):
        self.database = DatabaseSettings()
        self.kg = KnowledgeGraphSettings()
        self.neo4j = Neo4jSettings()
        self.ai = AISettings()
        self.bootstrap = BootstrapSettings()
        self.app = AppSettings()
    
    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  database_url={self.database.get_database_url()},\n"
            f"  kg_provider={self.kg.provider},\n"
            f"  neo4j_uri={self.neo4j.get_uri()},\n"
            f"  max_retries={self.ai.max_tool_call_retries},\n"
            f"  bootstrap_overwrite={self.bootstrap.should_overwrite},\n"
            f"  app_name={self.app.app_name}\n"
            f")"
        )


# 全局配置实例
settings = Settings()
