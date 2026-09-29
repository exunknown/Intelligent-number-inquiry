"""
应用主配置

定义 conf/app_config.yaml 在程序中的结构化配置对象
项目启动后会在这里一次性完成配置文件加载和类型化转换，其他模块只需要导入 app_config
就可以按属性方式读取日志 MySQL Qdrant Embedding Elasticsearch 和 LLM 配置
"""

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf


@dataclass
class File:
    """文件日志配置"""

    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    """控制台日志配置"""

    enable: bool
    level: str


# 把上面两个组合成一个类
@dataclass
class LoggingConfig:
    """日志总配置"""

    file: File
    console: Console


@dataclass
class DBConfig:
    """MySQL 连接配置"""

    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class SQLFallbackDBConfig(DBConfig):
    """SQL fallback 专用只读连接池配置。"""

    pool_size: int
    max_overflow: int
    pool_timeout_seconds: int
    pool_recycle_seconds: int


@dataclass
class QdrantConfig:
    """Qdrant 连接与向量维度配置"""

    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    """Embedding 服务配置"""

    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    """Elasticsearch 配置"""

    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    """大模型调用配置"""

    model_name: str
    api_key: str
    base_url: str


@dataclass
class IniConfig:
    """调用模型配置"""

    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str
    rerank_model: str


@dataclass
class SelectorConfig:
    """Schema Selector 的按需触发配置"""

    enabled: bool
    schema_token_threshold: int
    token_estimate_chars_per_token: float


@dataclass
class CubeConfig:
    """Cube 问数服务配置"""

    base_url: str
    api_secret: str
    timeout_seconds: float
    max_limit: int
    semantic_view: str


@dataclass
class AuthConfig:
    """OIDC 访问令牌校验配置"""

    enabled: bool
    issuer: str
    audience: str
    jwks_url: str
    jwks_cache_seconds: int
    clock_skew_seconds: int


@dataclass
class SQLSafetyConfig:
    """模型 SQL 的策略与执行资源预算。"""

    enabled: bool
    dialect: str
    max_sql_bytes: int
    max_ast_nodes: int
    max_nesting_depth: int
    max_ctes: int
    max_union_branches: int
    max_rows: int
    max_result_bytes: int
    max_execution_ms: int
    max_estimated_rows: int
    max_query_cost: float


@dataclass
class ResourceConfig:
    """问数请求的单实例资源预算。"""

    request_timeout_seconds: float
    max_request_body_bytes: int
    global_concurrency: int
    user_concurrency: int
    rate_limit: int
    rate_window_seconds: float
    dependency_max_retries: int
    retry_backoff_seconds: float
    max_llm_calls: int
    max_embedding_calls: int


@dataclass
class AppConfig:
    """项目级总配置入口"""

    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    db_sql_fallback: SQLFallbackDBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig
    ini: IniConfig
    selector: SelectorConfig
    cube: CubeConfig
    auth: AuthConfig
    sql_safety: SQLSafetyConfig
    resource: ResourceConfig


# 获取配置文件位置（为了不硬编码）：从当前文件位置回到项目根目录，再定位到 conf/app_config.yaml
#
project_root = Path(__file__).parents[2]
config_file = project_root / "conf" / "app_config.yaml"

# 先读取本地 .env，让 YAML 的环境配置读取到注入密钥
load_dotenv(project_root / ".env")

# 读取 YAML 配置内容
context = OmegaConf.load(config_file)
# 根据 AppConfig 生成结构化配置 schema
schema = OmegaConf.structured(AppConfig)
# 把配置结构和配置值合并，再转换成可以直接按属性访问的对象

# 本质是在做“先定义结构，再加载内容，最后把它们合并成一个配置对象”。
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

if __name__ == "__main__":
    # 简单测试：验证配置是否能正常读取
    print(app_config.es.host)
