from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)


class QdrantStore:
    """Qdrant collection lifecycle, dense upsert, and similarity search."""

    def __init__(
        self,
        collection_name: str,
        vector_size: int,
        client: QdrantClient | None = None,
        *,
        location: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.vector_size = vector_size
        if client is not None:
            self._client = client
        elif location is not None:
            self._client = QdrantClient(location=location)
        else:
            self._client = QdrantClient(location=":memory:")
        self._owns_client = client is None

    @property
    def client(self) -> QdrantClient:
        return self._client

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self.collection_name):
            return
        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )

    def upsert_embedding(
        self,
        vector: list[float],
        *,
        chunk_id: str,
        version_id: str,
        origin_type: str,
        unit_type: str,
        unit_number: int,
        table_id: str | None = None,
        image_id: str | None = None,
    ) -> None:
        self.ensure_collection()
        payload: dict[str, Any] = {
            "chunk_id": chunk_id,
            "version_id": version_id,
            "origin_type": origin_type,
            "unit_type": unit_type,
            "unit_number": unit_number,
        }
        if table_id is not None:
            payload["table_id"] = table_id
        if image_id is not None:
            payload["image_id"] = image_id

        # Qdrant local mode requires UUID-shaped string ids; derive deterministically from chunk_id.
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"openagent:chunk:{chunk_id}"))

        self._client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int = 10,
        version_id: str | None = None,
        version_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_collection()
        qf = None
        if version_ids:
            qf = Filter(
                must=[
                    FieldCondition(key="version_id", match=MatchAny(any=version_ids)),
                ]
            )
        elif version_id is not None:
            qf = Filter(
                must=[FieldCondition(key="version_id", match=MatchValue(value=version_id))]
            )

        res = self._client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qf,
            with_payload=True,
        )

        meta_keys = ("unit_type", "unit_number", "origin_type", "table_id", "image_id")
        out: list[dict[str, Any]] = []
        for p in res.points:
            pl = p.payload or {}
            payload_meta = {k: pl[k] for k in meta_keys if k in pl}
            out.append(
                {
                    "id": p.id,
                    "score": p.score,
                    "chunk_id": pl.get("chunk_id"),
                    "version_id": pl.get("version_id"),
                    "payload_meta": payload_meta,
                }
            )
        return out

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
