"""Keycloak Admin API 管理客户端配置。"""

from dataclasses import dataclass


@dataclass
class KeycloakAdminConfig:
    """Keycloak Admin API 管理客户端配置"""

    base_url: str
    realm: str
    client_id: str
    client_secret: str
    timeout_seconds: float
    token_cache_skew_seconds: float
