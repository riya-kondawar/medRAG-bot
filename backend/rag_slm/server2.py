import os
import shutil
import subprocess
import json
import uuid
import sys
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient # Recommended for FastAPI, but keeping your MongoClient
from pymongo import MongoClient
from dotenv import load_dotenv

# SQLite fix for Chroma
import pysqlite3
sys.modules["sqlite3"] = pysqlite3

from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_community.vectorstores import Chroma

load_dotenv()

app = FastAPI(title="MEDRAG - Real-Time Analysis")

# --- Global State ---
LATEST_SESSION_ID = None 

# --- Pydantic Models ---
class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None # Added back so it's optional
    top_k: int = 5

class Chunk(BaseModel):
    content: str
    source: str
    test_name: Optional[str] = None
    score: float

class AskResponse(BaseModel):
    answer: str
    chunks: List[Chunk]

# --- Middleware & Config ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PERSIST_DIR = "rag_slm/vectordb"
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
    global LATEST_SESSION_ID # Necessary to update the global variable
    
    session_id = str(uuid.uuid4()) 
    LATEST_SESSION_ID = session_id  
    
    temp_path = f"temp_{session_id}_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 1. OCR
        subprocess.run(["python", "rag_slm/ocr.py", "--input", temp_path, "--out", f"ocr_{session_id}.json"], check=True)
        # 2. Parse
        subprocess.run(["python", "rag_slm/parse.py", "--input", f"ocr_{session_id}.json", "--out", f"structured_{session_id}.json"], check=True)
        
        with open(f"ocr_{session_id}.json", "r") as f:
            ocr_result = json.load(f)   
            mongo_report_id = ocr_result.get("ocr_doc_id")
            actual_file_id = ocr_result.get("mongo_file_id")

        if not mongo_report_id:
            raise ValueError("ocr_doc_id missing from OCR output")

        # 3. Save Session
        session_data = {
            "session_id": session_id,
            "report_id": mongo_report_id, 
            "file_id": actual_file_id,
            "filename": file.filename,
            "created_at": datetime.utcnow()
        }
        mongo_client["medrag"]["sessions"].insert_one(session_data)

        # 4. Ingest
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
        for f in [temp_path, f"ocr_{session_id}.json", f"structured_{session_id}.json"]:
            if os.path.exists(f): os.remove(f)

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    # Determine which session to use
    s_id = None
    if req.session_id and req.session_id != "string":
        s_id = req.session_id
    else:
        s_id = LATEST_SESSION_ID

    if not s_id:
        # Use HTTP 400 for clarity
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No session ID provided and no recent upload found.")
    
    collection_name = f"sess_{s_id}"
    
    db = Chroma(
        persist_directory=PERSIST_DIR, 
        embedding_function=embeddings, 
        collection_name=collection_name
    )
    count = db._collection.count()
    if count == 0:
        return AskResponse(
            answer="No searchable content was found for this report.",
            chunks=[]
        )
    print(f"DEBUG: Collection {collection_name} has {count} items.")
    results = db.similarity_search_with_score(req.question, k=req.top_k)

    chunks = []
    for doc, score in results:
        chunks.append(Chunk(
            content=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            test_name=doc.metadata.get("test_name"),
            score=float(score)
        ))

    if not chunks or (len(chunks) == 1 and "Unknown" in chunks[0].content):
         return AskResponse(
            answer="I couldn't find any specific medical data in the report to answer that.",
            chunks=chunks
        )

    context = "\n\n".join([c.content for c in chunks])
    prompt = f"""You are a medical report analyzer. 
Use the following context to answer the question. If unsure, say you don't know.

CONTEXT:
{context}

QUESTION:
{req.question}

ANSWER:"""
    
    answer = llm.invoke(prompt).strip()
    return AskResponse(answer=answer, chunks=chunks)