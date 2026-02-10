import React, { useState } from 'react';
import { uploadFile } from '@/services/api'; 
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { UploadCloud, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import type { MedicalAnalysis } from '@/types';

interface FileUploadZoneProps {
  // 👇 Updated to accept sessionId
  onUploadSuccess: (analysis: MedicalAnalysis, sessionId: string) => void;
}

export function FileUploadZone({ onUploadSuccess }: FileUploadZoneProps) {
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus('uploading');
    try {
      const response = await uploadFile(file);
      if (response.status === "success") {
        setStatus('success');
        // 👇 Extract session_id from response and pass it up
        onUploadSuccess(response.analysis, response.session_id);
        setTimeout(() => setStatus('idle'), 3000);
      } else {
        throw new Error("Upload failed");
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
      setTimeout(() => setStatus('idle'), 4000);
    }
  };

  return (
    <Card className="p-8 border-dashed border-2 bg-slate-50/50 border-slate-200 hover:bg-slate-100 transition-all group cursor-pointer relative overflow-hidden">
      <div className="flex flex-col items-center justify-center gap-4 text-center relative z-10">
        {status === 'idle' && (
          <>
            <div className="p-4 bg-white rounded-full shadow-sm border border-slate-100 group-hover:scale-110 transition-transform text-blue-500">
              <UploadCloud size={32} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-700">Upload Medical Report</h3>
              <p className="text-xs text-slate-400 mt-1">Supports PDF, PNG, JPG (Max 10MB)</p>
            </div>
            <input type="file" className="hidden" id="main-upload" onChange={handleFileChange} accept=".pdf,.png,.jpg,.jpeg" />
            <Button variant="outline" size="sm" className="mt-2 bg-white" asChild>
              <label htmlFor="main-upload" className="cursor-pointer">Browse Files</label>
            </Button>
          </>
        )}
        {status === 'uploading' && (
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="animate-spin text-blue-600" size={32} />
            <p className="text-xs text-slate-500 font-medium animate-pulse">Analyzing Document...</p>
          </div>
        )}
        {status === 'success' && (
          <div className="flex flex-col items-center gap-2 text-green-600">
            <CheckCircle2 size={32} className="animate-bounce" />
            <p className="text-xs font-bold uppercase">Analysis Complete</p>
          </div>
        )}
        {status === 'error' && (
          <div className="flex flex-col items-center gap-2 text-red-600">
            <AlertCircle size={32} />
            <p className="text-xs font-bold">Upload Failed</p>
          </div>
        )}
      </div>
    </Card>
  );
}