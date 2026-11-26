import hashlib
import io
import os
from pathlib import Path
import chromadb
import fitz
from docx import Document as WordDocument
from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy import select
from app.database import ROOT
from app.models import Document

MAX_UPLOAD = 5 * 1024 * 1024

def openai_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "AI is not configured. Set OPENAI_API_KEY on the server.")
    return OpenAI(api_key=key, timeout=30, max_retries=1)

def collection():
    return chromadb.PersistentClient(path=os.getenv("CHROMA_PATH", str(ROOT / "chroma_data"))).get_or_create_collection("policies")

def extract(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return [("section 1", data.decode("utf-8"))]
    if suffix == ".pdf":
        with fitz.open(stream=data, filetype="pdf") as pdf:
            return [(f"page {number + 1}", page.get_text()) for number, page in enumerate(pdf)]
    if suffix == ".docx":
        doc = WordDocument(io.BytesIO(data))
        return [("section 1", "\n".join(paragraph.text for paragraph in doc.paragraphs))]
    raise HTTPException(422, "Only PDF, DOCX and TXT documents are supported")

def index_document(db, user_id, filename, data):
    filename = Path(filename.replace("\\", "/")).name
    if not filename or len(filename) > 200 or len(data) > MAX_UPLOAD or not data:
        raise HTTPException(422, "Invalid filename or document size")
    try:
        pages = extract(filename, data)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Unable to read document")
    chunks = []
    for location, text in pages:
        text = text.strip()
        for offset in range(0, len(text), 600):
            chunk = text[offset:offset + 700].strip()
            if chunk:
                chunks.append((location, chunk))
    if not chunks or len(chunks) > 500:
        raise HTTPException(422, "Document has no text or too many chunks")
    previous = db.scalars(select(Document).where(Document.filename == filename, Document.status == "ACTIVE")).all()
    version = max((doc.version for doc in previous), default=0) + 1
    doc = Document(filename=filename, sha256=hashlib.sha256(data).hexdigest(), version=version, status="INDEXING", uploaded_by=user_id)
    db.add(doc)
    db.commit()
    try:
        embeddings = openai_client().embeddings.create(model="text-embedding-3-small", input=[text for _, text in chunks])
        collection().add(ids=[f"{doc.id}-{index}" for index in range(len(chunks))], embeddings=[entry.embedding for entry in embeddings.data], documents=[text for _, text in chunks], metadatas=[{"document_id": doc.id, "filename": filename, "location": location, "version": version} for location, _ in chunks])
        for old in previous:
            old.status = "INACTIVE"
        doc.status = "ACTIVE"
        db.commit()
    except Exception:
        db.rollback()
        doc.status = "FAILED"
        db.commit()
        raise HTTPException(503, "Document indexing is unavailable")
    return {"id": doc.id, "filename": filename, "version": version, "chunks": len(chunks)}

def retrieve(db, question):
    active_ids = list(db.scalars(select(Document.id).where(Document.status == "ACTIVE")))
    if not active_ids:
        return []
    embedding = openai_client().embeddings.create(model="text-embedding-3-small", input=[question]).data[0].embedding
    result = collection().query(query_embeddings=[embedding], n_results=4, where={"document_id": {"$in": active_ids}}, include=["documents", "metadatas", "distances"])
    return [{"text": text, "filename": meta["filename"], "location": meta["location"], "chunk_id": chunk_id, "version": meta["version"]} for text, meta, chunk_id, distance in zip(result["documents"][0], result["metadatas"][0], result["ids"][0], result["distances"][0]) if distance < 1.4]