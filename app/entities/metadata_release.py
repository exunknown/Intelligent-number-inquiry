"""元数据发布 manifest 和状态实体。"""

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MetadataReleaseManifest:
    """一次元数据发布必须携带的不可变版本清单。"""

    release_version: str
    app_version: str
    db_migration_version: str
    cube_model_hash: str
    cube_compiler_id: str
    field_metadata_version: str
    qdrant_column_collection: str
    qdrant_metric_collection: str
    qdrant_cube_collection: str
    es_value_index: str
    embedding_model: str
    embedding_dimension: int
    prompt_version: str
    released_at: str

    def canonical_json(self) -> str:
        """返回字段顺序和编码均稳定的 JSON，用于审计和幂等判断。"""

        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        """计算 manifest 内容摘要，不把摘要自身放入输入。"""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MetadataReleaseRecord:
    """发布注册表中的状态快照。"""

    manifest: MetadataReleaseManifest
    manifest_sha256: str
    status: str
    error_code: str | None = None
