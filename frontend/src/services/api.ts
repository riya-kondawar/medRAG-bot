import axios from "axios";

// 🚀 PRODUCTION MODE
export const USE_MOCK = false; 

const API_BASE_URL = "https://carmen-bikini-ferry-cooling.trycloudflare.com"; 

const api = axios.create({
  baseURL: API_BASE_URL,
});

// --- Types ---
export interface Chunk {
  content: string;
  source: string;
  test_name?: string;
  score: number;
}

export interface MedicalAnalysis {
  patient_info: { 
    name?: string; 
    age_gender_raw?: string; 
    registration_date?: string; 
  };
  report_type: string;
  abnormal: Array<{
    name: string;
    result: any;
    unit: string;
    flag: string;
    ref_low: any;
    ref_high: any;
  }>;
}

export interface AskResponse {
  answer: string;
  chunks: Chunk[];
}

export interface UploadResponse {
  status: string;
  session_id: string;
  analysis: MedicalAnalysis;
}

export interface DeleteResponse {
  status: string;
  message: string;
}

// --- API FUNCTIONS (Connected to Cloudflare) ---

export const uploadFile = async (file: File): Promise<UploadResponse> => {
  // If we accidentally left mock mode on, warn the developer
  if (USE_MOCK) {
    console.warn("⚠️ WARNING: Application is still in Mock Mode.");
  }

  const formData = new FormData();
  formData.append("file", file);
  
  try {
    const res = await api.post("/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data; 
  } catch (error) {
    console.error("Upload Error:", error);
    throw error;
  }
};

export const askQuestion = async (question: string, sessionId: string | null): Promise<AskResponse> => {
  try {
    const res = await api.post("/ask", { 
      question, 
      session_id: sessionId 
    });
    return res.data;
  } catch (error) {
    console.error("Chat Error:", error);
    throw error;
  }
};

export const deleteSession = async (sessionId: string): Promise<DeleteResponse> => {
  if (USE_MOCK) {
    console.log(`🟡 MOCK DELETE (Session: ${sessionId})...`);
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({ status: "success", message: "Mock session deleted" });
      }, 1000);
    });
  }

  try {
    const res = await api.post("/delete_all", { session_id: sessionId });
    return res.data;
  } catch (error) {
    console.error("Delete Session Error:", error);
    throw error;
  }
};