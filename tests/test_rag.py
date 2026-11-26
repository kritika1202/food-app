from types import SimpleNamespace
from fastapi.testclient import TestClient
from app import rag
from app.database import SessionLocal
from app.main import app
from app.models import User
from sqlalchemy import select

def test_document_versions_and_citations(monkeypatch):
    class FakeEmbeddings:
        def create(self, model, input):
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])
    class FakeCollection:
        def __init__(self):
            self.rows = []
        def add(self, ids, embeddings, documents, metadatas):
            self.rows.extend(zip(ids, documents, metadatas))
        def query(self, query_embeddings, n_results, where, include):
            active = where["document_id"]["$in"]
            rows = [row for row in self.rows if row[2]["document_id"] in active]
            return {"ids": [[row[0] for row in rows]], "documents": [[row[1] for row in rows]], "metadatas": [[row[2] for row in rows]], "distances": [[0.1] * len(rows)]}
    fake_collection = FakeCollection()
    monkeypatch.setattr(rag, "openai_client", lambda: SimpleNamespace(embeddings=FakeEmbeddings()))
    monkeypatch.setattr(rag, "collection", lambda: fake_collection)
    with TestClient(app):
        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            first = rag.index_document(db, admin.id, "policy.txt", b"Old policy")
            second = rag.index_document(db, admin.id, "policy.txt", b"New policy")
            assert second["version"] == first["version"] + 1
            citations = rag.retrieve(db, "policy")
            assert len(citations) == 1
            assert citations[0]["text"] == "New policy"
            assert citations[0]["filename"] == "policy.txt"