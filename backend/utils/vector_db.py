import os
import threading
from typing import List, Optional, Dict, Any
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv("../../.env")

class _SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()
    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class PineconeSingleton(metaclass=_SingletonMeta):
    def __init__(self, api_key: Optional[str] = None, index_name: Optional[str] = None):
        self._api_key = api_key or os.getenv("PINECONE_API_KEY")
        self._index_name = index_name or os.getenv("PINECONE_INDEX")
        self._client = None
        self._index = None
        self._init_lock = threading.Lock()
        self._ensure_initialized()

    def _ensure_initialized(self):
        with self._init_lock:
            if self._client:
                return
            if not self._api_key:
                raise RuntimeError("PINECONE_API_KEY missing")
            self._client = Pinecone(api_key=self._api_key)
            if self._index_name:
                self._index = self._client.Index(self._index_name)

    def set_index(self, index_name: str):
        self._ensure_initialized()
        self._index_name = index_name
        self._index = self._client.Index(index_name)

    def create_index(self, index_name: str, dimension: int):
        self._ensure_initialized()
        existing = [i["name"] for i in self._client.list_indexes()]
        if index_name in existing:
            return
        self._client.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )

    def get_index(self):
        if not self._index:
            raise RuntimeError("Index not set")
        return self._index

    def upsert(self, vectors: List[Dict[str, Any]], namespace: Optional[str] = None):
        return self._index.upsert(vectors=vectors, namespace=namespace)

    def query(self, vector: List[float], top_k: int = 10, namespace: Optional[str] = None):
        return self._index.query(vector=vector, top_k=top_k, namespace=namespace)

    def fetch(self, ids: List[str], namespace: Optional[str] = None):
        return self._index.fetch(ids=ids, namespace=namespace)

    def delete(self, ids: Optional[List[str]] = None, namespace: Optional[str] = None, filter: Optional[Dict[str, Any]] = None):
        if ids:
            return self._index.delete(ids=ids, namespace=namespace)
        if filter:
            return self._index.delete(filter=filter, namespace=namespace)
        raise RuntimeError("Provide ids or filter")

    def index_stats(self):
        return self._index.describe_index_stats()
