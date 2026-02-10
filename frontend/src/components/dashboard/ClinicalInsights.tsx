import { ClipboardCheck, Lightbulb, Stethoscope, ArrowRight, HeartPulse } from "lucide-react";
import type { MedicalAnalysis } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button"; // <--- Added this missing import

export function ClinicalInsights({ analysis }: { analysis: MedicalAnalysis }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      
      {/* 1. Primary AI Summary */}
      <Card className="col-span-1 md:col-span-2 bg-gradient-to-r from-blue-600 to-blue-700 text-white border-none shadow-lg">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-bold uppercase tracking-widest opacity-90">
            <ClipboardCheck size={16} /> Clinical Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-medium leading-relaxed">
            The system detected <span className="font-bold bg-white/20 px-2 py-0.5 rounded">{analysis.abnormal.length} abnormal values</span> in your {analysis.report_type}. 
            The primary concern appears to be related to <span className="underline decoration-wavy decoration-white/50 underline-offset-4">{analysis.abnormal[0]?.name || "metabolic markers"}</span>.
          </p>
        </CardContent>
      </Card>

      {/* 2. Immediate Actions */}
      <Card className="bg-white border-l-4 border-l-amber-500 shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-slate-800">
            <Stethoscope className="text-amber-500" /> Recommended Actions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-3 items-start">
             <div className="w-6 h-6 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shrink-0 text-xs font-bold">1</div>
             <p className="text-sm text-slate-600">Schedule a follow-up with a <strong>General Physician</strong> within 7 days to review these findings.</p>
          </div>
          <div className="flex gap-3 items-start">
             <div className="w-6 h-6 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shrink-0 text-xs font-bold">2</div>
             <p className="text-sm text-slate-600">Retest <span className="font-semibold text-slate-800">{analysis.abnormal[0]?.name}</span> in 4 weeks to monitor trends.</p>
          </div>
        </CardContent>
      </Card>

      {/* 3. Lifestyle Adjustments */}
      <Card className="bg-white border-l-4 border-l-green-500 shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-slate-800">
            <HeartPulse className="text-green-500" /> Lifestyle & Wellness
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
           <div className="p-3 bg-green-50 rounded-lg border border-green-100">
             <h4 className="text-xs font-bold text-green-700 uppercase mb-1 flex items-center gap-1"><Lightbulb size={12}/> AI Tip</h4>
             <p className="text-sm text-green-800">Increasing hydration and reducing sodium intake may help stabilize these levels.</p>
           </div>
           <Button variant="ghost" className="w-full justify-between text-slate-400 hover:text-blue-600 text-xs">
              View detailed diet plan <ArrowRight size={14}/>
           </Button>
        </CardContent>
      </Card>

    </div>
  );
}