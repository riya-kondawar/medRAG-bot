import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DownloadCloud, User } from "lucide-react";
import { ClinicalInsights } from "./ClinicalInsights";
import type { MedicalAnalysis } from "@/types";
import { USE_MOCK } from "@/services/api"; 

export function AnalysisDashboard({ data }: { data: MedicalAnalysis }) {

  const handleDownload = () => {
    if (USE_MOCK) {
      console.log("Generating Mock Report...");
      
      const headers = ["Test Name", "Result", "Unit", "Flag", "Reference Range"];
      const rows = data.abnormal.map(item => 
        `"${item.name}","${item.result}","${item.unit}","${item.flag}","${item.ref_low}-${item.ref_high}"`
      );
      const csvContent = [headers.join(","), ...rows].join("\n");

      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `MOCK_REPORT_${data.patient_info.name || "PATIENT"}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      window.open("http://localhost:8000/download-report", "_blank");
    }
  };

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto animate-in fade-in zoom-in-95 duration-500">
      
      <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
           <div className="flex items-center gap-2 text-blue-600 mb-1">
              <User size={16} />
              <span className="text-xs font-bold uppercase tracking-wider">Patient Profile</span>
           </div>
           <h2 className="text-2xl font-bold text-slate-800">{data.patient_info?.name || "Unknown Patient"}</h2>
           <p className="text-sm text-slate-500">{data.patient_info?.age_gender_raw || "No metadata found"}</p>
        </div>
        
        <div className="flex gap-2 w-full md:w-auto">
           <Button 
              onClick={handleDownload} 
              className="w-full md:w-auto gap-2 bg-slate-900 text-white hover:bg-black transition-colors"
           >
              <DownloadCloud size={14} /> 
              {USE_MOCK ? "Download CSV (Mock)" : "Download Excel Report"}
           </Button>
        </div>
      </div>

      <Tabs defaultValue="findings" className="w-full">
        <TabsList className="w-full justify-start bg-transparent border-b rounded-none h-auto p-0 mb-6">
          <TabsTrigger value="findings" className="data-[state=active]:border-b-2 data-[state=active]:border-blue-600 data-[state=active]:shadow-none rounded-none px-6 py-3">Findings</TabsTrigger>
          <TabsTrigger value="insights" className="data-[state=active]:border-b-2 data-[state=active]:border-blue-600 data-[state=active]:shadow-none rounded-none px-6 py-3">AI Insights</TabsTrigger>
        </TabsList>
        
        <TabsContent value="findings" className="mt-0">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.abnormal && data.abnormal.length > 0 ? (
              data.abnormal.map((item, i) => (
                <div key={i} className="p-4 bg-white border border-slate-100 rounded-xl shadow-sm hover:shadow-md transition-all border-l-4 border-l-red-400">
                  <div className="flex justify-between items-start mb-2">
                    <p className="text-sm font-bold text-slate-700">{item.name}</p>
                    <Badge className={item.flag === 'H' ? 'bg-orange-500' : 'bg-blue-500'}>{item.flag}</Badge>
                  </div>
                  <div className="flex justify-between items-baseline mt-4">
                    <p className="text-xl font-mono text-red-600 font-bold">{item.result} <span className="text-xs text-slate-400 font-sans">{item.unit}</span></p>
                    <p className="text-xs text-slate-400">Ref: {item.ref_low}-{item.ref_high}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-full text-center py-12 bg-slate-50 rounded-xl border border-dashed">
                <p className="text-slate-400">No abnormal values detected.</p>
              </div>
            )}
          </div>
        </TabsContent>
        
        <TabsContent value="insights">
          <ClinicalInsights analysis={data} />
        </TabsContent>
      </Tabs>
    </div>
  );
}