import React, { useState, useRef, useEffect } from 'react';
import { 
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger 
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { MessageSquare, Send, Bot, User, Sparkles, Hash } from "lucide-react"; // Added Hash icon
import { askQuestion } from '@/services/api';
import type { AskResponse, Chunk } from '@/types';

export function ChatSheet({ contextActive, sessionId }: { contextActive: boolean, sessionId: string | null }) {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<{role: 'user' | 'ai', text: string, chunks?: Chunk[]}[]>([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
        scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const handleSend = async () => {
    if (!query.trim() || loading) return;
    const userMsg = query;
    setQuery("");
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setLoading(true);

    try {
      const data: AskResponse = await askQuestion(userMsg, sessionId);
      setMessages(prev => [...prev, { role: 'ai', text: data.answer, chunks: data.chunks }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'ai', text: "Connection error. Please try again." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button 
          className="fixed bottom-8 right-8 h-16 w-16 rounded-full shadow-2xl bg-blue-600 hover:bg-blue-700 z-50 transition-all hover:scale-110 flex items-center justify-center"
          disabled={!contextActive}
        >
          <MessageSquare size={28} />
          <span className="absolute top-0 right-0 h-4 w-4 bg-red-500 rounded-full border-2 border-white"></span>
        </Button>
      </SheetTrigger>
      
      <SheetContent className="w-full sm:w-[450px] flex flex-col p-0 h-full border-l shadow-2xl">
        <SheetHeader className="p-5 border-b bg-white shrink-0">
          <SheetTitle className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg text-blue-600">
                <Bot size={20} />
            </div>
            <div>
                <h3 className="text-sm font-bold text-slate-800">Medical Assistant</h3>
                <p className="text-[10px] text-green-600 font-medium flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span> Online & Secure
                </p>
            </div>
          </SheetTitle>
          
          {/* 👇 UPDATED SECTION: Full Session ID Display */}
          <div className="mt-2 p-2 bg-slate-50 rounded border border-slate-100">
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest mb-1 flex items-center gap-1">
               <Hash size={10} /> Active Session ID
            </p>
            <SheetDescription className="text-[10px] font-mono text-slate-600 break-all select-all leading-tight">
               {sessionId || "Waiting for upload..."}
            </SheetDescription>
          </div>
          
        </SheetHeader>

        <ScrollArea className="flex-1 p-5 bg-slate-50 overflow-y-auto">
          {messages.length === 0 && (
             <div className="h-full flex flex-col items-center justify-center text-center opacity-60 p-6 pt-20">
               <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4 text-blue-500">
                 <Sparkles size={32} />
               </div>
               <h4 className="font-bold text-slate-700 mb-1">How can I help?</h4>
               <p className="text-xs text-slate-500 max-w-[200px]">
                 Ask me about your results.
               </p>
             </div>
          )}
          
          <div className="space-y-6 pb-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}>
                    {m.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                </div>
                <div className={`max-w-[80%] space-y-2`}>
                    <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${
                        m.role === 'user' 
                        ? 'bg-blue-600 text-white rounded-tr-none' 
                        : 'bg-white border border-slate-200 text-slate-700 rounded-tl-none'
                    }`}>
                        {m.text}
                    </div>
                    {m.chunks && m.chunks.length > 0 && (
                        <div className="flex gap-2 flex-wrap">
                            {m.chunks.map((c, idx) => (
                                <Badge key={idx} variant="secondary" className="bg-slate-200/50 text-slate-500 text-[9px]">
                                    Source: {c.test_name || "Page " + (idx+1)}
                                </Badge>
                            ))}
                        </div>
                    )}
                </div>
              </div>
            ))}
            {loading && <div className="p-4"><span className="animate-pulse text-xs text-slate-400">Thinking...</span></div>}
            <div ref={scrollRef} />
          </div>
        </ScrollArea>

        <div className="p-4 bg-white border-t shrink-0">
          <div className="relative">
            <Input 
                className="pr-12 py-6 rounded-full border-slate-200 bg-slate-50"
                placeholder="Ask a question..." 
                value={query} 
                onChange={e => setQuery(e.target.value)} 
                onKeyDown={e => e.key === 'Enter' && handleSend()} 
            />
            <Button 
                size="icon" 
                className="absolute right-1.5 top-1.5 h-9 w-9 rounded-full bg-blue-600 hover:bg-blue-700"
                onClick={handleSend} 
                disabled={loading}
            >
                <Send size={16} />
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
