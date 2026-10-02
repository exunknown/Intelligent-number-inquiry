"""Cube 候选语义模型编译和校验适配器。"""

import hashlib
import json
from dataclasses import dataclass

from app.entities.cube_member import extract_cube_members
from app.entities.semantic_model import SemanticModelSnapshot
from app.services.cube_dynamic_model import build_cube_model


@dataclass(frozen=True)
class CubeCompilationResult:
    """一次候选模型编译的不可变结果。"""

    release_version: str
    compiler_id: str
    model_hash: str
    model: dict[str, object]
    member_count: int


class CubeSemanticModelCompiler:
    """把语义快照编译成受限 Cube 模型，并返回可审计摘要。"""

    compiler_id = "cube-semantic-compiler/1"

    def __init__(self, cube_repository=None):
        self.cube_repository = cube_repository

    async def compile(self, snapshot: SemanticModelSnapshot) -> CubeCompilationResult:
        model = build_cube_model(snapshot)
        runtime_compiler_id = None
        if self.cube_repository is not None:
            metadata = await self.cube_repository.get_metadata()
            runtime_members, runtime_compiler_id = extract_cube_members(
                metadata, "ecommerce"
            )
            runtime_names = {member.name for member in runtime_members}
            candidate_names = {member.qualified_name for member in snapshot.members}
            missing_names = sorted(candidate_names - runtime_names)
            if missing_names:
                raise ValueError(
                    "Cube runtime does not expose candidate members: "
                    + ", ".join(missing_names)
                )
        canonical = json.dumps(
            model,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return CubeCompilationResult(
            release_version=snapshot.release_version,
            compiler_id=(
                f"{self.compiler_id}+{runtime_compiler_id}"
                if runtime_compiler_id
                else self.compiler_id
            ),
            model_hash=hashlib.sha256(canonical).hexdigest(),
            model=model,
            member_count=len(snapshot.members),
        )
