import os
import json
import argparse
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
import sys
import sqlite3
sys.modules["sqlite3"] = sqlite3
from bson import ObjectId

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

from utils_docs import build_documents
from pymongo import MongoClient

from pathlib import Path
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

load_dotenv()
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable not set")

MONGO_DB = "medrag"
OCR_COLLECTION = "ocr_reports"
STRUCTURED_COLLECTION = "structured_reports"
SESSION_COLLECTION = "sessions"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def structured_test_to_document(
    test: Dict[str, Any],
    *,
    report_id: str,
    session_id: str,
) -> Optional[Document]:
    test_name = normalize_text(
        test.get("test_name")
        or test.get("name")
        or test.get("test")
        or test.get("investigation")
    )
    value = normalize_text(test.get("value") or test.get("result"))
    unit = normalize_text(test.get("unit") or test.get("units"))

    reference_range = normalize_text(test.get("reference_range"))
    if not reference_range:
        low = test.get("ref_low")
        high = test.get("ref_high")
        if low not in (None, "") and high not in (None, ""):
            reference_range = f"{low} - {high}"

    if not any([test_name, value, unit, reference_range]):
        return None

    if not test_name:
        test_name = "Unknown Test"

    if not value:
        value = "NA"
    if not unit:
        unit = "NA"
    if not reference_range:
        reference_range = "NA"

    # Canonical structured chunk format required by downstream retrieval.
    content = f"{test_name}: {value} {unit} (Normal: {reference_range})"

    metadata: Dict[str, Any] = {
        "source": str(report_id),
        "test_name": test_name,
        "type": "structured",
    }
    if session_id:
        metadata["session_id"] = session_id

    confidence = safe_float(test.get("confidence"))
    if confidence is not None:
        metadata["confidence"] = confidence

    return Document(page_content=content, metadata=metadata)


def load_structured_reports(
    client: MongoClient,
    *,
    session_id: Optional[str],
    report_id: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if session_id:
        query["session_id"] = session_id
    if report_id:
        query["report_id"] = str(report_id)

    cursor = client[MONGO_DB][STRUCTURED_COLLECTION].find(query).sort("created_at", -1)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def build_documents_from_structured_reports(
    reports: List[Dict[str, Any]],
    *,
    default_session_id: str,
) -> List[Document]:
    docs: List[Document] = []

    for report in reports:
        report_id = str(report.get("report_id") or report.get("_id") or "unknown_report")
        session_id = normalize_text(report.get("session_id") or default_session_id)
        parsed_data = report.get("parsed_data") or report.get("parsed") or report

        tests = parsed_data.get("tests") if isinstance(parsed_data, dict) else None
        if not isinstance(tests, list):
            continue

        for test in tests:
            if not isinstance(test, dict):
                continue
            doc = structured_test_to_document(
                test,
                report_id=report_id,
                session_id=session_id,
            )
            if doc:
                docs.append(doc)

    return docs


def load_ocr_reports_for_fallback(
    client: MongoClient,
    *,
    session_id: Optional[str],
    report_id: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    ocr_col = client[MONGO_DB][OCR_COLLECTION]

    if report_id:
        try:
            cursor = ocr_col.find({"_id": ObjectId(str(report_id))})
        except Exception:
            cursor = ocr_col.find({"_id": str(report_id)})
        reports = list(cursor)
        if reports:
            return reports[:limit] if limit else reports
        print(f"OCR_FALLBACK_REPORT_ID_MISS=1 REPORT_ID={report_id}")

    report_object_ids: List[ObjectId] = []
    if session_id:
        sessions = list(client[MONGO_DB][SESSION_COLLECTION].find({"session_id": session_id}))
        for session in sessions:
            rid = session.get("ocr_report_id") or session.get("report_id")
            if not rid:
                continue
            try:
                report_object_ids.append(ObjectId(str(rid)))
            except Exception:
                continue

    if not report_object_ids:
        cursor = ocr_col.find({})
        reports = list(cursor)
        return reports[:limit] if limit else reports

    cursor = ocr_col.find({"_id": {"$in": report_object_ids}})
    reports = list(cursor)
    return reports[:limit] if limit else reports


def build_documents_from_ocr_reports(reports: List[Dict[str, Any]], *, session_id: str) -> List[Document]:
    docs: List[Document] = []
    for report in reports:
        raw_text = (report.get("merged_full_text") or "").strip()
        if not raw_text:
            continue
        docs.append(
            Document(
                page_content=raw_text,
                metadata={
                    "source": str(report.get("_id") or "unknown_source"),
                    "type": "raw_ocr",
                    "session_id": session_id,
                },
            )
        )
    return docs

def load_reports_from_mongo(limit: int | None = None) -> List[Dict[str, Any]]:
    client = MongoClient(MONGO_URI)
    col = client[MONGO_DB][OCR_COLLECTION]

    # cursor = col.find({"status": "OCR_COMPLETED"})
    cursor = col.find({})
    if limit:
        cursor = cursor.limit(limit)

    reports = list(cursor)
    client.close()

    if not reports:
        raise RuntimeError("No OCR reports found in MongoDB")

    return reports



def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def discover_json_inputs(path: str) -> List[str]:
    if os.path.isfile(path) and path.lower().endswith(".json"):
        return [path]

    if os.path.isdir(path):
        files = []
        for root, _, fs in os.walk(path):
            for fn in fs:
                if fn.lower().endswith(".json"):
                    files.append(os.path.join(root, fn))
        return sorted(files)

    raise FileNotFoundError(f"Invalid JSON path: {path}")


def chunk_documents(docs: List[Document], size: int, overlap: int) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    return splitter.split_documents(docs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="Structured JSON file or directory")
    ap.add_argument("--persist_dir", default="rag_slm/vectordb")
    ap.add_argument("--collection", required=True, help="Session-specific collection name")
    ap.add_argument("--embed_model", default="nomic-embed-text")
    ap.add_argument("--chunk_size", type=int, default=900)
    ap.add_argument("--chunk_overlap", type=int, default=120)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--mongo", action="store_true", help="Load OCR JSONs from MongoDB")
    ap.add_argument("--mongo_limit", type=int, default=None, help="Limit MongoDB docs")
    ap.add_argument("--report_id", help="The specific MongoDB Object ID to ingest")
    ap.add_argument("--session_id", help="Session ID for structured ingestion")
    args = ap.parse_args()
    if args.mongo and args.json:
        raise RuntimeError("Use either --mongo or --json, not both")

    if not args.mongo and not args.json:
        raise RuntimeError("Provide either --mongo or --json")


    if args.reset and os.path.exists(args.persist_dir):
        import shutil
        shutil.rmtree(args.persist_dir, ignore_errors=True)
        print(f"RESET_VECTORDB=1 PATH={args.persist_dir}")

    all_docs: List[Document] = []
    ingest_mode = "unknown"

    if args.mongo:
        print("INGEST_INPUT=MONGO")
        client = MongoClient(MONGO_URI)
        structured_reports = load_structured_reports(
            client,
            session_id=args.session_id,
            report_id=args.report_id,
            limit=args.mongo_limit,
        )

        all_docs = build_documents_from_structured_reports(
            structured_reports,
            default_session_id=args.session_id or "",
        )

        if all_docs:
            ingest_mode = "structured"
            print(f"INGEST_MODE={ingest_mode}")
            print(f"STRUCTURED_REPORTS_FOUND={len(structured_reports)}")
            print(f"STRUCTURED_DOCS_BUILT={len(all_docs)}")
        else:
            ingest_mode = "ocr_fallback"
            print(f"INGEST_MODE={ingest_mode}")
            print("STRUCTURED_DOCS_BUILT=0")

            ocr_reports = load_ocr_reports_for_fallback(
                client,
                session_id=args.session_id,
                report_id=args.report_id,
                limit=args.mongo_limit,
            )
            all_docs = build_documents_from_ocr_reports(
                ocr_reports,
                session_id=args.session_id or "",
            )
            print(f"OCR_REPORTS_FOUND={len(ocr_reports)}")
            print(f"OCR_DOCS_BUILT={len(all_docs)}")

        client.close()

    else:
        ingest_mode = "json"
        json_files = discover_json_inputs(args.json)
        print(f"JSON_INPUT_FILES={len(json_files)}")

        for jf in json_files:
            report = load_json_file(jf)
            report_id = str(
                report.get("report_id")
                or report.get("source")
                or report.get("mongo_file_id")
                or jf
            )
            docs = build_documents(report, report_id=report_id)

            # Support direct ingestion of parser v2 schema in JSON mode.
            if not docs and isinstance(report.get("tests"), list):
                docs = build_documents_from_structured_reports(
                    [
                        {
                            "session_id": "",
                            "report_id": report_id,
                            "parsed_data": report,
                        }
                    ],
                    default_session_id="",
                )

            all_docs.extend(docs)
            print(f"JSON_FILE={os.path.basename(jf)} DOCS={len(docs)}")

        if not all_docs:
            raise RuntimeError("No documents generated from JSON inputs")

    chunks = chunk_documents(all_docs, args.chunk_size, args.chunk_overlap)
    if not chunks:
        raise RuntimeError("Ingestion produced 0 chunks")

    print(f"CHUNKS_CREATED={len(chunks)}")

    for idx, chunk in enumerate(chunks[:3]):
        preview = chunk.page_content.replace("\n", " ").strip()
        if len(preview) > 160:
            preview = preview[:160] + "..."
        print(
            f"CHUNK_SAMPLE_{idx}_TYPE={chunk.metadata.get('type')} "
            f"TEST={chunk.metadata.get('test_name', '')} TEXT={preview}"
        )

    embeddings = OllamaEmbeddings(model=args.embed_model)

    vector_store = Chroma(
        collection_name=args.collection,
        persist_directory=args.persist_dir,
        embedding_function=embeddings,
    )
    vector_store.add_documents(chunks)

    print("INGEST_COMPLETE=1")
    print(f"CHUNKS_STORED={len(chunks)}")
    print(f"COLLECTION={args.collection}")
    print(f"PERSIST_DIR={args.persist_dir}")
    print(f"INGEST_MODE_FINAL={ingest_mode}")


if __name__ == "__main__":
    main()
    