import os
import threading
from pymongo import MongoClient
from typing import Any, Dict, Optional, List
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


class MongoDB(metaclass=_SingletonMeta):
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self._uri = uri or os.getenv("MONGO_URI")
        self._db_name = db_name or os.getenv("MONGO_DB")
        if not self._uri or not self._db_name:
            raise RuntimeError("MONGO_URI and MONGO_DB must be provided")
        self._client = MongoClient(self._uri)
        self._db = self._client[self._db_name]

    def collection(self, name: str):
        return self._db[name]

    def insert_one(self, collection: str, document: Dict[str, Any]):
        return self.collection(collection).insert_one(document)

    def insert_many(self, collection: str, documents: List[Dict[str, Any]]):
        return self.collection(collection).insert_many(documents)

    def find_one(self, collection: str, query: Dict[str, Any], projection: Optional[Dict[str, int]] = None):
        return self.collection(collection).find_one(query, projection)

    def find(self, collection: str, query: Dict[str, Any], projection: Optional[Dict[str, int]] = None, limit: Optional[int] = None):
        cursor = self.collection(collection).find(query, projection)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def update_one(self, collection: str, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        return self.collection(collection).update_one(query, update, upsert=upsert)

    def update_many(self, collection: str, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        return self.collection(collection).update_many(query, update, upsert=upsert)

    def delete_one(self, collection: str, query: Dict[str, Any]):
        return self.collection(collection).delete_one(query)

    def delete_many(self, collection: str, query: Dict[str, Any]):
        return self.collection(collection).delete_many(query)

    def aggregate(self, collection: str, pipeline: List[Dict[str, Any]]):
        return list(self.collection(collection).aggregate(pipeline))

    def count(self, collection: str, query: Dict[str, Any]):
        return self.collection(collection).count_documents(query)

    def drop_collection(self, collection: str):
        return self._db.drop_collection(collection)

    def list_collections(self):
        return self._db.list_collection_names()
