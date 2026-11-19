"""RAG layer: ChromaDB vector store with CPU-friendly MiniLM embeddings (no torch needed)."""
import logging

import chromadb
import numpy as np
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .config import settings

logger = logging.getLogger(__name__)

_client = None
_ef = None
_ef_failed = False


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _client


def _get_ef():
    global _ef, _ef_failed
    if _ef is None and not _ef_failed:
        try:
            _ef = DefaultEmbeddingFunction()
        except Exception as e:
            logger.warning("Embedding model unavailable (%s); falling back to lexical matching", e)
            _ef_failed = True
    return _ef


def embed_texts(texts: list[str]) -> np.ndarray | None:
    ef = _get_ef()
    if ef is None or not texts:
        return None
    try:
        return np.array(ef(texts), dtype=np.float32)
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def job_text(job: dict) -> str:
    skills = ", ".join(job.get("skills") or [])
    return f"{job.get('title', '')} at {job.get('company', '')}. Skills: {skills}. {(job.get('description') or '')[:1500]}"


def profile_text(profile: dict) -> str:
    skills = ", ".join(profile.get("skills") or [])
    roles = ", ".join(profile.get("target_roles") or [])
    hist = " ".join(f"{w.get('title', '')} {w.get('summary', '')}" for w in (profile.get("work_history") or [])[:3])
    proj = " ".join(f"{p.get('name', '')} {p.get('description', '')}" for p in (profile.get("projects") or [])[:4])
    return (f"{profile.get('current_role', 'AI Engineer')} with {profile.get('experience_years', 0)} years experience. "
            f"Target roles: {roles}. Skills: {skills}. {hist} {proj}")


def index_jobs(jobs: list[dict]):
    if not jobs:
        return
    try:
        col = _get_client().get_or_create_collection("jobs")
        col.upsert(
            ids=[str(j["id"]) for j in jobs],
            documents=[job_text(j) for j in jobs],
            metadatas=[{"title": j.get("title", ""), "company": j.get("company", ""),
                        "source": j.get("source", "")} for j in jobs],
        )
    except Exception as e:
        logger.warning("Job indexing failed: %s", e)


def index_profile(profile: dict):
    try:
        col = _get_client().get_or_create_collection("profile")
        text = profile_text(profile)
        col.upsert(ids=["profile-summary"], documents=[text], metadatas={"kind": "summary"})
        raw = profile.get("raw_text") or ""
        chunks = [raw[i:i + 800] for i in range(0, min(len(raw), 8000), 800)]
        if chunks:
            col.upsert(ids=[f"resume-chunk-{i}" for i in range(len(chunks))],
                       documents=chunks, metadatas=[{"kind": "resume"} for _ in chunks])
    except Exception as e:
        logger.warning("Profile indexing failed: %s", e)


def retrieve_profile_context(query: str, k: int = 3) -> list[str]:
    try:
        col = _get_client().get_or_create_collection("profile")
        res = col.query(query_texts=[query], n_results=k)
        return res["documents"][0] if res.get("documents") else []
    except Exception:
        return []


def semantic_search(query: str, k: int = 20) -> list[dict]:
    try:
        col = _get_client().get_or_create_collection("jobs")
        res = col.query(query_texts=[query], n_results=k)
        out = []
        for i, jid in enumerate(res["ids"][0]):
            out.append({"job_id": int(jid), "distance": res["distances"][0][i],
                        "document": res["documents"][0][i]})
        return out
    except Exception as e:
        logger.warning("Semantic search failed: %s", e)
        return []