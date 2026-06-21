import os
import shutil
import subprocess
import json
import uuid
import sys
import io
import gridfs
import logging
from typing import List, Optional
from datetime import datetime
from pathlib import Path
from bson import ObjectId

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv

# SQLite fix for Chroma (Windows)
import sqlite3
sys.modules["sqlite3"] = sqlite3

from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_community.vectorstores import Chroma


# -----------------------------------------------------------------------------
# Paths / Env (IMPORTANT: make everything deterministic regardless of CWD)
# -----------------------------------------------------------------------------
RAG_DIR = Path(__file__).resolve().parent              # .../backend/rag_slm
BACKEND_DIR = RAG_DIR.parent                           # .../backend
ENV_PATH = RAG_DIR / ".env"                            # .../backend/rag_slm/.env

load_dotenv(dotenv_path=ENV_PATH, override=True)

# Debug prints (safe)
print("ENV_PATH =", str(ENV_PATH))
print("ENV exists =", ENV_PATH.exists())
print("CWD =", os.getcwd())
print("PYTHON =", sys.executable)
print("MONGO_URI loaded =", bool(os.getenv("MONGO_URI")))

logging.basicConfig(
    level=os.getenv("MEDRAG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("medrag.server")

# Use a stable persist dir (do NOT rely on os.getcwd())
PERSIST_DIR = str(RAG_DIR / "vectordb")

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="MEDRAG - Real-Time Analysis")

# CORS (add both localhost and 127.0.0.1 origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LLM / Embeddings
embeddings = OllamaEmbeddings(model="nomic-embed-text")
llm = OllamaLLM(model="gemma3:1b", temperature=0.2)

# Mongo
MONGO_URI = (os.environ.get("MONGO_URI") or "").strip().strip('"').strip("'")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable not set")

mongo_client = MongoClient(MONGO_URI)


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    session_id: str
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


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def run_cmd(cmd: List[str], *, cwd: Path) -> str:
    """
    Run a subprocess and return stdout.
    If it fails, raise RuntimeError with stdout/stderr so we can debug quickly.
    Forces UTF-8 so Windows console doesn't crash on emojis.
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"                 # force UTF-8 mode
    env["PYTHONIOENCODING"] = "utf-8"       # force stdout/stderr encoding

    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"  CMD: {' '.join(cmd)}\n"
            f"  CWD: {cwd}\n\n"
            f"STDOUT:\n{p.stdout}\n\n"
            f"STDERR:\n{p.stderr}\n"
        )
    return p.stdout


def safe_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "MEDRAG backend running"}


@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    logger.info("upload_start session_id=%s filename=%s", session_id, file.filename)

    # Save upload to a deterministic temp file inside backend dir
    temp_path = BACKEND_DIR / f"temp_{session_id}_{file.filename}"
    ocr_json = BACKEND_DIR / f"ocr_{session_id}.json"
    structured_json = BACKEND_DIR / f"structured_{session_id}.json"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Absolute script paths + same python env + fixed cwd
        ocr_py = RAG_DIR / "ocr.py"
        parse_py = RAG_DIR / "parse.py"
        ingest_py = RAG_DIR / "ingest.py"
        py = sys.executable  # IMPORTANT: same interpreter as uvicorn

        # 1) OCR
        run_cmd(
            [py, str(ocr_py), "--input", str(temp_path), "--out", str(ocr_json)],
            cwd=BACKEND_DIR,
        )

        # 2) Parse
        run_cmd(
            [py, str(parse_py), "--input", str(ocr_json), "--out", str(structured_json)],
            cwd=BACKEND_DIR,
        )

        # Read OCR output IDs
        with open(ocr_json, "r", encoding="utf-8") as f:
            ocr_result = json.load(f)

        mongo_report_id = str(ocr_result.get("ocr_doc_id") or "")
        actual_file_id = ocr_result.get("mongo_file_id")

        if not mongo_report_id:
            raise ValueError("ocr_doc_id missing from OCR output")

        # Return structured analysis JSON + persist in Mongo before ingestion.
        with open(structured_json, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)

        analysis_data["report_id"] = str(analysis_data.get("report_id") or mongo_report_id)

        structured_doc = {
            "session_id": session_id,
            "report_id": analysis_data["report_id"],
            "parsed_data": analysis_data,
            "created_at": datetime.utcnow(),
        }
        structured_insert = mongo_client["medrag"]["structured_reports"].insert_one(structured_doc)
        logger.info(
            "structured_saved session_id=%s report_id=%s tests=%s structured_doc_id=%s",
            session_id,
            analysis_data["report_id"],
            len(analysis_data.get("tests", [])),
            structured_insert.inserted_id,
        )

        # 3) Save Session mapping
        session_data = {
            "session_id": session_id,
            "report_id": analysis_data["report_id"],
            "ocr_report_id": mongo_report_id,
            "file_id": actual_file_id,
            "filename": file.filename,
            "structured_doc_id": str(structured_insert.inserted_id),
            "created_at": datetime.utcnow(),
        }
        mongo_client["medrag"]["sessions"].insert_one(session_data)
        logger.info(
            "session_saved session_id=%s report_id=%s ocr_report_id=%s",
            session_id,
            analysis_data["report_id"],
            mongo_report_id,
        )

        # 4) Ingest into Chroma (capture stdout/stderr)
        logger.info("ingest_start session_id=%s collection=%s", session_id, f"sess_{session_id}")
        ingest_stdout = run_cmd(
            [
                py,
                str(ingest_py),
                "--mongo",
                "--collection",
                f"sess_{session_id}",
                "--session_id",
                session_id,
                "--report_id",
                str(analysis_data["report_id"]),
                "--persist_dir",
                str(RAG_DIR / "vectordb"),
            ],
            cwd=BACKEND_DIR,
        )
        logger.info(
            "ingest_output session_id=%s details=%s",
            session_id,
            ingest_stdout.replace("\n", " | ").strip(),
        )
        logger.info("ingest_complete session_id=%s", session_id)

        return {"status": "success", "session_id": session_id, "analysis": analysis_data}

    except Exception as e:
        # Return rich error to client for debugging
        logger.exception("upload_failed session_id=%s filename=%s", session_id, file.filename)
        return {"status": "error", "message": str(e), "session_id": session_id}

    finally:
        # Cleanup temp files
        safe_remove(temp_path)
        safe_remove(ocr_json)
        safe_remove(structured_json)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    logger.info("ask_start session_id=%s top_k=%s question_len=%s", req.session_id, req.top_k, len(req.question or ""))
    collection_name = f"sess_{req.session_id}"

    db = Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    count = db._collection.count()
    if count == 0:
        logger.warning("ask_no_data session_id=%s", req.session_id)
        return AskResponse(answer="No medical data found for this session.", chunks=[])

    results = db.similarity_search_with_score(req.question, k=req.top_k)
    structured_hits = sum(1 for doc, _ in results if doc.metadata.get("type") == "structured")
    logger.info(
        "ask_retrieval session_id=%s hits=%s structured_hits=%s",
        req.session_id,
        len(results),
        structured_hits,
    )

    chunks = [
        Chunk(
            content=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            test_name=doc.metadata.get("test_name"),
            score=float(score),
        )
        for doc, score in results
    ]

    context = "\n\n".join([c.content for c in chunks])
    prompt = f"Context:\n{context}\n\nQuestion: {req.question}\n\nAnswer:"
    answer = llm.invoke(prompt).strip()

    return AskResponse(answer=answer, chunks=chunks)


@app.post("/delete_all")
async def delete_all(req: DeleteRequest):
    try:
        session_id = req.session_id
        db = mongo_client["medrag"]
        fs = gridfs.GridFS(db)

        records = list(db["sessions"].find({"session_id": session_id}))
        if not records:
            return {"status": "warning", "message": "No records found for this session."}

        db["structured_reports"].delete_many({"session_id": session_id})

        for rec in records:
            if "file_id" in rec:
                try:
                    fs.delete(ObjectId(rec["file_id"]))
                except Exception:
                    pass

            if "report_id" in rec:
                try:
                    db["structured_reports"].delete_many({"report_id": str(rec["report_id"])})
                except Exception:
                    pass
                try:
                    db["ocr_reports"].delete_many({"_id": ObjectId(rec["report_id"])})
                except Exception:
                    pass
                try:
                    db["ocr_results"].delete_many({"_id": ObjectId(rec["report_id"])})
                except Exception:
                    pass

        # Delete Chroma collection
        try:
            coll_name = f"sess_{session_id}"
            db_chroma = Chroma(
                persist_directory=PERSIST_DIR,
                embedding_function=embeddings,
                collection_name=coll_name,
            )
            db_chroma.delete_collection()
        except Exception:
            pass

        db["sessions"].delete_many({"session_id": session_id})
        return {"status": "success", "message": f"Session {session_id} deleted successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/files/{session_id}")
async def get_session_files(session_id: str):
    files = list(mongo_client["medrag"]["sessions"].find({"session_id": session_id}))
    return {
        "files": [{"filename": f["filename"], "file_id": str(f.get("file_id"))} for f in files]
    }