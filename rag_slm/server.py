from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

app = FastAPI(title="MEDRAG - RAG + SLM (Ollama gemma3:1b)")

PERSIST_DIR = "vectordb"
COLLECTION = "medical_reports"

embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectordb = Chroma(
    persist_directory=PERSIST_DIR,
    embedding_function=embeddings,
    collection_name=COLLECTION,
)

llm = Ollama(model="gemma3:1b", temperature=0.2)


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    source: Optional[str] = None
    report_type: Optional[str] = None


class Chunk(BaseModel):
    content: str
    source: str
    report_type: str
    doc_kind: str
    test_name: Optional[str] = None
    score: float


class AskResponse(BaseModel):
    answer: str
    chunks: List[Chunk]


def build_filter(req: AskRequest):
    f = {}
    if req.source:
        f["source"] = req.source
    if req.report_type:
        f["report_type"] = req.report_type
    return f if f else None


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    filt = build_filter(req)
    results = vectordb.similarity_search_with_score(req.question, k=req.top_k, filter=filt)

    context_blocks = []
    chunks: List[Chunk] = []

    for doc, score in results:
        md = doc.metadata or {}
        context_blocks.append(doc.page_content)
        chunks.append(
            Chunk(
                content=doc.page_content[:1200],
                source=md.get("source", "unknown"),
                report_type=md.get("report_type", "UNKNOWN"),
                doc_kind=md.get("doc_kind", "unknown"),
                test_name=md.get("test_name"),
                score=float(score),
            )
        )

    context = "\n\n---\n\n".join(context_blocks)

    prompt = f"""You are a medical lab report assistant.
Answer ONLY using the given CONTEXT.

Rules:
- If info is missing, say: "I don't have that information in this report."
- Prefer exact numbers with units + reference ranges.
- Do not diagnose. If user asks meaning, explain generally and advise consulting a doctor if needed.

CONTEXT:
{context}

QUESTION:
{req.question}

ANSWER (short, structured):
"""

    answer = llm.invoke(prompt).strip()
    return AskResponse(answer=answer, chunks=chunks)
