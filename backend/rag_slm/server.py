import os
import shutil
import subprocess
import json
import uuid
import sys
import io
import gridfs
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv

# SQLite fix for Chroma
import pysqlite3
sys.modules["sqlite3"] = pysqlite3

from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_community.vectorstores import Chroma

load_dotenv()

app = FastAPI(title="MEDRAG - Real-Time Analysis")

# --- Pydantic Models ---
class AskRequest(BaseModel):
    question: str
    session_id: str  # Now required for subsequent calls
    top_k: int = 5

class Chunk(BaseModel):
    content: str
    source: str
    test_name: Optional[str] = None
    score: float

class AskResponse(BaseModel):
    answer: str
    chunks: List[Chunk]

class DeleteRequest(BaseModel):
    session_id: str

# --- Middleware & Config ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSIST_DIR = os.path.join(os.getcwd(), "rag_slm", "vectordb")  
embeddings = OllamaEmbeddings(model="nomic-embed-text")
llm = OllamaLLM(model="gemma3:1b", temperature=0.2)

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ MONGO_URI environment variable not set")
mongo_client = MongoClient(MONGO_URI)

# --- Routes ---

@app.get("/")
def root():
    return {"status": "MEDRAG backend running"}

@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4()) 
    temp_path = f"temp_{session_id}_{file.filename}"
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 1. OCR & Parse
        subprocess.run(["python", "rag_slm/ocr.py", "--input", temp_path, "--out", f"ocr_{session_id}.json"], check=True)
        subprocess.run(["python", "rag_slm/parse.py", "--input", f"ocr_{session_id}.json", "--out", f"structured_{session_id}.json"], check=True)
        
        with open(f"ocr_{session_id}.json", "r") as f:
            ocr_result = json.load(f)   
            mongo_report_id = ocr_result.get("ocr_doc_id")
            actual_file_id = ocr_result.get("mongo_file_id")

        if not mongo_report_id:
            raise ValueError("ocr_doc_id missing from OCR output")

        # 2. Save Session Mapping to MongoDB
        session_data = {
            "session_id": session_id,
            "report_id": mongo_report_id, 
            "file_id": actual_file_id,
            "filename": file.filename,
            "created_at": datetime.utcnow()
        }
        mongo_client["medrag"]["sessions"].insert_one(session_data)

        # 3. Ingest into Chroma
        subprocess.run([
            "python", "rag_slm/ingest.py", 
            "--mongo", 
            "--collection", f"sess_{session_id}",
            "--report_id", mongo_report_id
        ], check=True)

        with open(f"structured_{session_id}.json", "r") as f:
            analysis_data = json.load(f)
        
        return {
            "status": "success",    
            "session_id": session_id,
            "analysis": analysis_data
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        # Local file cleanup
        for f in [temp_path, f"ocr_{session_id}.json", f"structured_{session_id}.json"]:
            if os.path.exists(f): os.remove(f)

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    collection_name = f"sess_{req.session_id}"
    
    db = Chroma(
        persist_directory=PERSIST_DIR, 
        embedding_function=embeddings, 
        collection_name=collection_name
    )
    
    count = db._collection.count()
    if count == 0:
        return AskResponse(answer="No medical data found for this session.", chunks=[])

    results = db.similarity_search_with_score(req.question, k=req.top_k)

    chunks = [
        Chunk(
            content=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            test_name=doc.metadata.get("test_name"),
            score=float(score)
        ) for doc, score in results
    ]

    context = "\n\n".join([c.content for c in chunks])
    prompt = f"Context:\n{context}\n\nQuestion: {req.question}\n\nAnswer:"
    
    answer = llm.invoke(prompt).strip()
    return AskResponse(answer=answer, chunks=chunks)

@app.post("/delete_all")
async def delete_all(req: DeleteRequest):
    """Wipes all database records and Chroma collections for a session."""
    try:
        session_id = req.session_id
        db = mongo_client["medrag"]
        fs = gridfs.GridFS(db)

        # 1. Find all file references
        records = list(db["sessions"].find({"session_id": session_id}))
        
        if not records:
            return {"status": "warning", "message": "No records found for this session."}

        for rec in records:
            # Delete GridFS PDF
            if "file_id" in rec:
                try:
                    fs.delete(ObjectId(rec["file_id"]))
                except: pass
            
            # Delete Structured JSON in Mongo
            if "report_id" in rec:
                db["structured_reports"].delete_many({"_id": ObjectId(rec["report_id"])})
                # Also delete from raw OCR results if they are in a different collection
                db["ocr_results"].delete_many({"_id": ObjectId(rec["report_id"])})

        # 2. Delete ChromaDB Collection
        try:
            coll_name = f"sess_{session_id}"
            db_chroma = Chroma(
                persist_directory=PERSIST_DIR, 
                embedding_function=embeddings, 
                collection_name=coll_name
            )
            db_chroma.delete_collection()
        except:
            pass

        # 3. Final Session record cleanup
        db["sessions"].delete_many({"session_id": session_id})

        return {"status": "success", "message": f"Session {session_id} deleted successfully."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/session/files/{session_id}")
async def get_session_files(session_id: str):
    files = list(mongo_client["medrag"]["sessions"].find({"session_id": session_id}))
    return {
        "files": [
            {"filename": f["filename"], "file_id": str(f["file_id"])} 
            for f in files
        ]
    }