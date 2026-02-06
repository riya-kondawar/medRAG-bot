# 🏥 MedRag: Intelligent Medical Report Analysis & RAG System

**MedRag** is a high-performance, locally-hosted medical document analysis platform. It leverages **Retrieval-Augmented Generation (RAG)** and **Small Language Models (SLMs)** to parse complex lab reports (PDF/Images), extract structured data, and provide real-time clinical insights and conversational assistance.

---

## 🌟 Key Features

* **Real-Time End-to-End Pipeline:** Automated flow from file upload to OCR, structured parsing, and vector ingestion.
* **OCR Engine:** Utilizes **PaddleOCR** with specialized CV2 preprocessing for high-accuracy extraction from lab tables.
* **SLM Intelligence:** Powered by **Gemma-3-1b** via **Ollama** for local, privacy-compliant medical summarization and Q&A.
* **Clinical Dashboard:** Instant visualization of patient metadata and abnormal (H/L) findings.
* **Evidence Transparency:** Clickable source citations showing the exact raw text chunks used for AI responses.
* **Export & Persistence:** Research-ready module for exporting findings into JSON and Excel formats for audit logs.

---

## 🏗️ Technical Architecture

The project is divided into two primary environments:

### 1. Backend (Python/FastAPI)

* **Web Framework:** FastAPI with `python-multipart` for high-speed file streaming.
* **Vector Database:** ChromaDB for persistent document embeddings.
* **LLM Orchestration:** LangChain (`langchain-ollama`, `langchain-chroma`).
* **Processing Layers:**
* `ocr.py`: Document-to-image conversion (PyMuPDF) and text extraction (PaddleOCR).
* `parse.py`: Rule-based regex and heuristic engine to structure raw text into medical JSON.
* `ingest.py`: Semantic chunking and embedding generation using `nomic-embed-text`.



### 2. Frontend (React/TypeScript)

* **UI Library:** ShadCN UI & Tailwind CSS v4.
* **State Management:** React Hooks (useState/useEffect) for real-time dashboard synchronization.
* **Icons:** Lucide-React.
* **API Client:** Axios with custom TypeScript interfaces matching Pydantic backend models.

---

## 📂 Project Structure

```text
MedRag/
├── rag_slm/                # Core RAG & API logic
│   ├── server.py           # FastAPI entry point & CORS
│   ├── ocr.py              # PaddleOCR & CV2 Preprocessing
│   ├── parse.py            # Structured Medical Parser
│   ├── ingest.py           # VectorDB Ingestion script
│   └── utils_docs.py       # Metadata & Normalization helpers
├── slm_guidance/           # SLM Prompting & Guardrails
│   ├── prompts.py          # Clinical persona & constraints
│   └── ollama_client.py    # LLM interaction wrapper
├── frontend/               # React + ShadCN UI
│   ├── src/
│   │   ├── services/       # API (Axios) definitions
│   │   ├── components/     # UI Components (Dashboard, Chat)
│   │   └── App.tsx         # Main Orchestration logic
└── requirements.txt        # Backend dependencies

```

---

## 🚀 Getting Started

### Prerequisites

* [Ollama](https://ollama.ai/) installed and running.
* `gemma3:1b` and `nomic-embed-text` models pulled:
```bash
ollama pull gemma3:1b
ollama pull nomic-embed-text

```



### Backend Setup

1. **Navigate to root:** `cd MedRag`
2. **Create Virtual Environment:** `python -m venv venv`
3. **Activate venv:** `venv\Scripts\activate` (Windows)
4. **Install Dependencies:**
```bash
pip install fastapi uvicorn paddleocr paddlepaddle-tiny langchain-ollama langchain-chroma python-multipart pymupdf opencv-python

```


5. **Run Server:** ```bash
python -m uvicorn rag_slm.server:app --reload --port 8000
```


```



### Frontend Setup

1. **Navigate to frontend:** `cd frontend`
2. **Install Packages:** `npm install`
3. **Run Dev Server:** `npm run dev`

---

## 🛠️ Usage Flow

1. **Upload:** Use the Sidebar to upload a lab report (PDF/PNG).
2. **Real-Time Analysis:** The sidebar automatically populates with patient data and a flagged "Abnormal Findings" list.
3. **Chat:** Ask questions like *"Explain my TSH levels"* or *"What lifestyle changes should I make?"*
4. **Verify:** Click on "Evidence" badges to see the exact text extracted from the report.

---

## ⚖️ Disclaimer

*This software is a proof-of-concept. It is not intended to replace professional medical advice, diagnosis, or treatment. Local LLM outputs can hallucinate; always verify data against the original document.*

---
