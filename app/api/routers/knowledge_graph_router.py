"""Agent 管理页知识图谱只读接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_knowledge_graph_query_service
from app.api.schemas.knowledge_graph_schema import (
    KnowledgeGraphEdgeResponse,
    KnowledgeGraphNodeListResponse,
    KnowledgeGraphNodeResponse,
    KnowledgeGraphNodeType,
    KnowledgeGraphPathResponse,
    KnowledgeGraphReleaseListResponse,
    KnowledgeGraphReleaseResponse,
    KnowledgeGraphSubgraphResponse,
)
from app.security.dependencies import require_api_permission
from app.services.knowledge_graph_query_service import (
    KnowledgeGraphNodeNotFoundError,
    KnowledgeGraphQueryService,
    KnowledgeGraphReleaseNotFoundError,
)

knowledge_graph_router = APIRouter()
_require_read = require_api_permission("api:semantic-model", "read")


def _node_response(node) -> KnowledgeGraphNodeResponse:
    return KnowledgeGraphNodeResponse(
        node_id=node.node_id,
        node_type=node.node_type,
        title=node.title,
        description=node.description,
        metadata=KnowledgeGraphQueryService.safe_node_metadata(node),
        source=node.source,
        confidence=node.confidence,
        release_version=node.release_version,
    )


def _release_response(record: dict) -> KnowledgeGraphReleaseResponse:
    return KnowledgeGraphReleaseResponse(**record)


@knowledge_graph_router.get(
    "/api/admin/knowledge-graph/releases",
    response_model=KnowledgeGraphReleaseListResponse,
)
async def list_knowledge_graph_releases_handler(
    service: Annotated[
        KnowledgeGraphQueryService, Depends(get_knowledge_graph_query_service)
    ],
    _auth=Depends(_require_read),
) -> KnowledgeGraphReleaseListResponse:
    try:
        records, active_version = await service.list_releases()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="knowledge graph service unavailable",
        ) from exc
    return KnowledgeGraphReleaseListResponse(
        items=[_release_response(record) for record in records],
        active_release_version=active_version,
        backend=service.backend,
    )


@knowledge_graph_router.get(
    "/api/admin/knowledge-graph/nodes",
    response_model=KnowledgeGraphNodeListResponse,
)
async def search_knowledge_graph_nodes_handler(
    service: Annotated[
        KnowledgeGraphQueryService, Depends(get_knowledge_graph_query_service)
    ],
    _auth=Depends(_require_read),
    release_version: str | None = Query(None, min_length=1, max_length=64),
    q: str = Query("", max_length=128),
    node_type: KnowledgeGraphNodeType | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
) -> KnowledgeGraphNodeListResponse:
    try:
        version, nodes, total = await service.search_nodes(
            release_version,
            q,
            node_type,
            limit,
            offset,
        )
    except KnowledgeGraphReleaseNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="knowledge graph release not found"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="knowledge graph service unavailable",
        ) from exc
    return KnowledgeGraphNodeListResponse(
        items=[_node_response(node) for node in nodes],
        total=total,
        release_version=version,
        backend=service.backend,
    )


@knowledge_graph_router.get(
    "/api/admin/knowledge-graph/subgraph",
    response_model=KnowledgeGraphSubgraphResponse,
)
async def expand_knowledge_graph_handler(
    service: Annotated[
        KnowledgeGraphQueryService, Depends(get_knowledge_graph_query_service)
    ],
    _auth=Depends(_require_read),
    seed_node_id: str = Query(..., min_length=1, max_length=192),
    release_version: str | None = Query(None, min_length=1, max_length=64),
    max_hops: int = Query(2, ge=1, le=2),
    max_nodes: int = Query(80, ge=1, le=200),
    max_paths: int = Query(100, ge=1, le=200),
) -> KnowledgeGraphSubgraphResponse:
    try:
        version, nodes, edges, paths, partial = await service.expand_subgraph(
            release_version,
            seed_node_id,
            max_hops,
            max_nodes,
            max_paths,
        )
    except KnowledgeGraphReleaseNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="knowledge graph release not found"
        ) from exc
    except KnowledgeGraphNodeNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="knowledge graph node not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="knowledge graph service unavailable",
        ) from exc
    return KnowledgeGraphSubgraphResponse(
        nodes=[_node_response(node) for node in nodes],
        edges=[
            KnowledgeGraphEdgeResponse(
                edge_id=edge.edge_id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                edge_type=edge.edge_type,
                weight=edge.weight,
                source=edge.source,
                release_version=edge.release_version,
            )
            for edge in edges
        ],
        paths=[
            KnowledgeGraphPathResponse(
                node_ids=list(path.node_ids),
                edge_ids=list(path.edge_ids),
                score=path.score,
            )
            for path in paths
        ],
        release_version=version,
        backend=service.backend,
        partial=partial,
    )
