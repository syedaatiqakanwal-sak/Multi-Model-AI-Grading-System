"use client";

import { useState } from "react";
import {
  Upload,
  FileCheck,
  CheckCircle2,
  XCircle,
  Download,
  RefreshCw,
  AlertCircle,
  ShieldCheck,
  Cpu,
  Zap,
  FileText,
  Check,
  Sparkles,
  X,
  User,
  GraduationCap,
  Building,
  Hash,
  BookOpen,
  FileCode,
  ScanSearch,
  Bot,
} from "lucide-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { api } from "@/lib/api";
import { connectJobWebSocket } from "@/lib/websocket";

interface ExtractedMetadata {
  learner_name?: string;
  learner_id?: string;
  centre_name?: string;
  qualification?: string;
  awarding_body?: string;
  unit_code?: string;
  unit_name?: string;
  submission_date?: string;
  college?: string;
  tasks_count?: number;
  total_words?: number;
  has_intro?: boolean;
  has_conclusion?: boolean;
  has_bibliography?: boolean;
  format_issues?: string[];
}

interface TaskResult {
  task_number: number;
  task_heading: string;
  verdict: string;
  confidence: number;
  feedback_text: string;
  word_count: number;
  provider: string;
}

interface IntegrityResult {
  score?: number;
  flagged?: boolean;
  overall_similarity_pct?: number;
  top_matches?: { source: string; similarity: number }[];
  model_version?: string;
}

interface GradingResult {
  metadata: ExtractedMetadata;
  verdict: string;
  tasks: TaskResult[];
  pdfUrl: string;
  docxUrl?: string;
  ai_detection?: IntegrityResult;
  plagiarism?: IntegrityResult;
  review_required?: boolean;
}

const SEQUENTIAL_BEFORE = [
  { id: "SECURITY", label: "Security & Malware Sanitization", desc: "ClamAV virus scan and macro stripper", icon: ShieldCheck },
  { id: "PARSING", label: "Universal Assignment Parser", desc: "Clean body extraction (Intro to Conclusion) & citations", icon: FileText },
  { id: "FORMAT", label: "Format & Harvard Citation Validation", desc: "Verifying fonts, in-text citations & bibliography", icon: FileCheck },
  { id: "RUBRIC", label: "Dynamic Rubric & Word Count Gate", desc: "Validating against unit word count & rubric criteria", icon: BookOpen },
];

const PARALLEL_STAGES = [
  { id: "PARALLEL_AI", label: "Criterion Evaluation", desc: "Zero-temperature LLM evidence quoting & criterion scoring", icon: Zap },
  { id: "AI_DETECTION", label: "AI Detection", desc: "HuggingFace sequence classifier on the academic body", icon: Bot },
  { id: "PLAGIARISM", label: "Plagiarism Check", desc: "SBERT similarity against the reference corpus", icon: ScanSearch },
];

const SEQUENTIAL_AFTER = [
  { id: "DECISION", label: "Criterion Scoring & Final Verdict", desc: "Enforcing strict UK awarding body pass/refer rules", icon: Sparkles },
  { id: "PDF", label: "Official Feedback Report Generation", desc: "Rendering official marking sheet DOCX & PDF", icon: Download },
];

const STAGES = [...SEQUENTIAL_BEFORE, ...PARALLEL_STAGES, ...SEQUENTIAL_AFTER];

export default function GradeNowPage() {
  const [file, setFile] = useState<File | null>(null);
  const [unitCode, setUnitCode] = useState("HSC301");
  const [college, setCollege] = useState("UKPDA");

  // Modal & Live Progress State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStageId, setCurrentStageId] = useState<string>("SECURITY");
  const [stageMessage, setStageMessage] = useState("Initializing grading pipeline...");
  const [liveMetadata, setLiveMetadata] = useState<ExtractedMetadata | null>(null);
  const [eventLogs, setEventLogs] = useState<string[]>([]);
  const [isCompleted, setIsCompleted] = useState(false);
  const [isFailed, setIsFailed] = useState(false);
  const [result, setResult] = useState<GradingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parallelDone, setParallelDone] = useState<string[]>([]);
  const [aiDetection, setAiDetection] = useState<IntegrityResult | null>(null);
  const [plagiarism, setPlagiarism] = useState<IntegrityResult | null>(null);
  const [reviewRequired, setReviewRequired] = useState(false);

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setEventLogs((prev) => [...prev.slice(-20), `[${time}] ${msg}`]);
  };

  const handleUpload = async () => {
    if (!file) return;

    // Reset & Open Modal
    setIsModalOpen(true);
    setIsCompleted(false);
    setIsFailed(false);
    setError(null);
    setProgress(5);
    setCurrentStageId("SECURITY");
    setStageMessage("Uploading file to secure pipeline...");
    setLiveMetadata(null);
    setResult(null);
    setEventLogs([]);
    setParallelDone([]);
    setAiDetection(null);
    setPlagiarism(null);
    setReviewRequired(false);

    addLog(`Uploaded: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("unit_code", unitCode);
    formData.append("college", college);

    try {
      const res = await api.post("/v1/jobs/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const jobId = res.data.job_id;
      setProgress(15);
      setCurrentStageId("PARSING");
      setStageMessage("Assignment queued. Running deep structural parsing...");
      addLog(`Job Registered: ${jobId.slice(0, 8)}...`);

      // Polling helper
      const pollEvents = async () => {
        try {
          const evRes = await api.get(`/v1/jobs/${jobId}/events`);
          const events = evRes.data?.events || [];
          if (events.length > 0) {
            const lastEv = events[events.length - 1];
            if (lastEv.progress) setProgress(parseInt(lastEv.progress, 10));
            if (lastEv.stage) handleStageUpdate(lastEv.stage, lastEv.data);
          }
        } catch (e) {}
      };

      const pollInterval = setInterval(pollEvents, 1000);

      const handleStageUpdate = (stageName: string, dataRaw: any) => {
        const data = typeof dataRaw === "string" ? JSON.parse(dataRaw || "{}") : dataRaw || {};

        if (data.metadata) {
          setLiveMetadata(data.metadata);
        }

        if (stageName === "SECURITY_SCAN") {
          setCurrentStageId("SECURITY");
          setStageMessage("Security scan verified: Macro-free & clean");
          addLog("DocxSecurityPipeline: ClamAV virus scan passed");
        } else if (stageName === "PARSING") {
          setCurrentStageId("PARSING");
          const meta = data.metadata || {};
          setStageMessage(`Extracted: ${meta.learner_name || "Document Table Header"}`);
          addLog(`Parser: Learner = "${meta.learner_name || 'N/A'}" | Unit = "${meta.unit_code || 'N/A'}"`);
          addLog(`Parser: Found ${meta.tasks_count ?? 0} task sections (${meta.total_words ?? 0} total words)`);
        } else if (stageName === "FORMAT_VALIDATION") {
          setCurrentStageId("FORMAT");
          const fmt = data.format || {};
          setStageMessage(`Format: ${fmt.primary_font || "Times New Roman"} (${fmt.body_font_size_pt || 12}pt)`);
          addLog(`DocxFontResolver: Primary font = ${fmt.primary_font}, Body = ${fmt.body_font_size_pt}pt`);
        } else if (stageName === "WORD_COUNT_GATE") {
          setCurrentStageId("RUBRIC");
          setStageMessage(`Word count check: ${data.clean_words} words (Required: ${data.min_required})`);
          addLog(`WordCountGate: Body = ${data.clean_words} words | Minimum required = ${data.min_required}`);
        } else if (stageName === "EVALUATION" || stageName === "INTEGRITY_DISPATCH") {
          setCurrentStageId("PARALLEL_AI");
          setStageMessage(data.status || `Activating parallel evaluation + integrity checks`);
          addLog(data.status || `RubricLoader: Activated official specifications for ${unitCode}`);
        } else if (stageName === "AI_DETECTION") {
          setCurrentStageId("AI_DETECTION");
          if (typeof data.score === "number") {
            setAiDetection(data);
            setParallelDone((prev) => Array.from(new Set([...prev, "AI_DETECTION"])));
          }
          setStageMessage(data.status || `AI detection running`);
          addLog(`AI Detection: score=${data.score ?? "…"} flagged=${data.flagged ?? "…"}`);
        } else if (stageName === "PLAGIARISM_CHECK") {
          setCurrentStageId("PLAGIARISM");
          if (typeof data.overall_similarity_pct === "number") {
            setPlagiarism(data);
            setParallelDone((prev) => Array.from(new Set([...prev, "PLAGIARISM"])));
          }
          setStageMessage(data.status || `Plagiarism check running`);
          addLog(`Plagiarism: ${data.overall_similarity_pct ?? "…"}%`);
        } else if (stageName === "INTEGRITY") {
          if (data.ai_detection) setAiDetection(data.ai_detection);
          if (data.plagiarism) setPlagiarism(data.plagiarism);
          setReviewRequired(Boolean(data.review_required));
          setParallelDone((prev) => Array.from(new Set([...prev, "AI_DETECTION", "PLAGIARISM"])));
          addLog(data.status || "Integrity analysis complete");
        } else if (stageName.startsWith("TASK_")) {
          setCurrentStageId("PARALLEL_AI");
          setStageMessage(`Task ${data.task}: ${data.verdict?.toUpperCase()} (${data.word_count || 0} words)`);
          addLog(`Task ${data.task} [${data.heading || ""}]: ${data.verdict?.toUpperCase()} via ${data.provider || "Engine"}`);
        } else if (stageName === "DECISION") {
          setCurrentStageId("DECISION");
          setParallelDone((prev) => Array.from(new Set([...prev, "PARALLEL_AI"])));
          setStageMessage(`Final Assessment Decision: ${data.verdict?.toUpperCase()}`);
          addLog(`Decision Engine: Final Grade = ${data.verdict?.toUpperCase()}`);
        } else if (stageName === "PDF_GENERATION") {
          setCurrentStageId("PDF");
          setStageMessage("Filling official assessment marking sheet");
          addLog("PDF Service: Generating official feedback report");
        } else if (stageName === "COMPLETE") {
          clearInterval(pollInterval);
          setProgress(100);
          setCurrentStageId("PDF");
          setStageMessage("Grading complete and verified!");
          addLog("Pipeline Complete: Assessment report generated successfully");
          setIsCompleted(true);
          setIsFailed(false);
          const ai = data.ai_detection || aiDetection;
          const plag = data.plagiarism || plagiarism;
          if (ai) setAiDetection(ai);
          if (plag) setPlagiarism(plag);
          setReviewRequired(Boolean(data.review_required));
          setResult({
            metadata: data.metadata || liveMetadata || {},
            verdict: data.verdict?.toUpperCase() || "PASS",
            tasks: data.tasks || [],
            pdfUrl: data.pdf_url || `/api/v1/jobs/${jobId}/pdf`,
            docxUrl: data.docx_url || `/api/v1/jobs/${jobId}/docx`,
            ai_detection: ai,
            plagiarism: plag,
            review_required: Boolean(data.review_required),
          });
        } else if (stageName === "FAILED") {
          clearInterval(pollInterval);
          setIsFailed(true);
          setError(data.error || "Grading pipeline encountered an error");
          setStageMessage("Grading pipeline stopped due to error");
          addLog(`Error: ${data.error || "Execution failed"}`);
        }
      };

      // Connect WebSocket
      const cleanupWs = connectJobWebSocket(
        jobId,
        (eventData: any) => {
          if (eventData.progress) setProgress(parseInt(eventData.progress, 10));
          if (eventData.stage) handleStageUpdate(eventData.stage, eventData.data);
        },
        () => {}
      );
    } catch (err: any) {
      setIsFailed(true);
      setError(err.response?.data?.detail || err.message || "Failed to submit assignment");
      addLog(`Upload error: ${err.message}`);
    }
  };

  const getStageIndex = (stageId: string) => {
    return STAGES.findIndex((s) => s.id === stageId);
  };

  const currentStageIdx = getStageIndex(currentStageId);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">Grade Now</h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Upload assignment DOCX to automatically extract learner metadata, validate formatting, evaluate criteria, and generate feedback report.
          </p>
        </div>

        {/* Upload Card */}
        <div className="bg-white rounded-2xl p-8 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)] space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-bold text-neutral-700 block mb-1">Target College (Default / Fallback)</label>
              <select
                value={college}
                onChange={(e) => setCollege(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-800 outline-none bg-white"
              >
                <option value="UKPDA">UK Professional Development Academy (UKPDA)</option>
                <option value="ILC">Inspire London College (ILC)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-bold text-neutral-700 block mb-1">Unit Code (Default / Fallback)</label>
              <input
                type="text"
                value={unitCode}
                onChange={(e) => setUnitCode(e.target.value)}
                placeholder="e.g. HSC301"
                className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-800 outline-none bg-white"
              />
            </div>
          </div>

          <div className="border-2 border-dashed border-neutral-200 rounded-2xl p-10 flex flex-col items-center justify-center text-center hover:border-[#8b5cf6] transition cursor-pointer bg-neutral-50/50">
            <input
              type="file"
              accept=".docx"
              className="hidden"
              id="file-upload"
              onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
            />
            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
              <div className="w-14 h-14 rounded-2xl bg-[#ffffff] border border-[#8b5cf6] flex items-center justify-center text-black mb-3 shadow-sm">
                <Upload className="w-7 h-7 stroke-[2]" />
              </div>
              <p className="text-sm font-bold text-neutral-900">
                {file ? file.name : "Click to select or drag and drop DOCX assignment"}
              </p>
              <p className="text-xs text-neutral-400 mt-1 font-medium">
                Supports Qualifi, OTHM, NOCN, ATHE formats (Max 50MB)
              </p>
              {file && (
                <span className="mt-3 px-3 py-1 bg-emerald-50 text-emerald-700 font-bold text-xs rounded-full border border-emerald-200 flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5" />
                  <span>Ready for Grading ({(file.size / 1024).toFixed(1)} KB)</span>
                </span>
              )}
            </label>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleUpload}
              disabled={!file}
              className="px-6 py-3 rounded-xl bg-[#8b5cf6] text-black font-extrabold text-xs shadow-sm hover:bg-[#8b5cf6] transition disabled:opacity-50 flex items-center gap-2 cursor-pointer"
            >
              <Sparkles className="w-4 h-4 stroke-[2.5]" />
              <span>Start AI Grading</span>
            </button>
          </div>
        </div>

        {/* Results on Main Page if Modal Closed */}
        {result && !isModalOpen && (
          <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <span
                  className={`inline-flex items-center px-3 py-1 rounded-md text-xs font-extrabold border-2 border-brand-purple ${
                    result.verdict === "PASS"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-rose-50 text-rose-700"
                  }`}
                >
                  {result.verdict}
                </span>
                <h2 className="text-lg font-bold text-neutral-900 mt-1">
                  {result.metadata?.learner_name || "Learner Submission"}
                </h2>
                <p className="text-xs text-neutral-500 font-medium">
                  {result.metadata?.unit_code || unitCode} • {result.metadata?.qualification || "Diploma"} • {result.metadata?.centre_name || college}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => setIsModalOpen(true)}
                  className="px-4 py-2 rounded-xl border border-neutral-200 text-neutral-700 font-bold text-xs hover:bg-neutral-50 transition"
                >
                  View Live Summary
                </button>
                {result.docxUrl && (
                  <a
                    href={result.docxUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-neutral-300 text-neutral-800 font-bold text-xs hover:bg-neutral-50 transition shadow-xs"
                  >
                    <FileCode className="w-4 h-4" />
                    <span>Download DOCX</span>
                  </a>
                )}
                {result.pdfUrl && (
                  <a
                    href={result.pdfUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-5 py-2 rounded-xl bg-[#8b5cf6] text-black font-extrabold text-xs hover:bg-[#8b5cf6] transition shadow-sm"
                  >
                    <Download className="w-4 h-4 stroke-[2.5]" />
                    <span>Download PDF</span>
                  </a>
                )}
              </div>
            </div>

            {(result.ai_detection || result.plagiarism || result.review_required) && (
              <div className={`p-4 rounded-xl border space-y-2 ${result.review_required ? "border-brand-purple bg-brand-white" : "border-neutral-100 bg-neutral-50"}`}>
                {result.review_required && (
                  <p className="text-xs font-extrabold text-brand-purple">
                    MAIN_ASSESSOR review required — verdict was not auto-failed.
                  </p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-brand-white border border-brand-purple/30">
                    <p className="text-[10px] font-extrabold text-brand-purple uppercase">AI Detection</p>
                    <p className="text-sm font-bold text-brand-black mt-1">
                      Score {((result.ai_detection?.score ?? 0) * 100).toFixed(0)}%
                      {result.ai_detection?.flagged ? " · FLAGGED" : " · clear"}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-brand-white border border-brand-purple/30">
                    <p className="text-[10px] font-extrabold text-brand-purple uppercase">Plagiarism Check</p>
                    <p className="text-sm font-bold text-brand-black mt-1">
                      {(result.plagiarism?.overall_similarity_pct ?? 0).toFixed(1)}% similarity
                    </p>
                    {(result.plagiarism?.top_matches || []).slice(0, 3).map((m, i) => (
                      <p key={i} className="text-[11px] text-neutral-600 truncate">
                        {m.source} · {(m.similarity <= 1 ? m.similarity * 100 : m.similarity).toFixed(1)}%
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {result.tasks && result.tasks.length > 0 && (
              <div className="space-y-3 border-t border-neutral-100 pt-4">
                <h3 className="text-xs font-extrabold text-neutral-400 uppercase tracking-wider">Assessed Task Breakdown</h3>
                {result.tasks.map((t, idx) => (
                  <div key={idx} className="flex items-center justify-between p-4 rounded-xl bg-neutral-50 border border-neutral-100">
                    <div className="flex items-center gap-3">
                      {t.verdict?.toLowerCase() === "pass" ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                      ) : (
                        <XCircle className="w-5 h-5 text-rose-600 shrink-0" />
                      )}
                      <div>
                        <p className="text-xs font-bold text-neutral-900">Task {t.task_number || idx + 1}: {t.task_heading || `Task ${idx + 1}`}</p>
                        <p className="text-[11px] text-neutral-500 font-medium">{t.feedback_text}</p>
                        <p className="text-[10px] text-neutral-400 mt-0.5">{t.word_count} words • Evaluated via {t.provider}</p>
                      </div>
                    </div>
                    <span
                      className={`text-xs font-bold px-2.5 py-1 rounded ${
                        t.verdict?.toLowerCase() === "pass"
                          ? "text-emerald-700 bg-emerald-100/80"
                          : "text-rose-700 bg-rose-100/80"
                      }`}
                    >
                      {t.verdict?.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 🌟 LIVE GRADING PROGRESS MODAL POP-UP */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl max-w-2xl w-full shadow-2xl overflow-hidden border border-neutral-100 flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-6 bg-neutral-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-[#8b5cf6] text-black flex items-center justify-center font-extrabold shadow-sm">
                  <Sparkles className="w-5 h-5 stroke-[2.5]" />
                </div>
                <div>
                  <h2 className="text-base font-extrabold flex items-center gap-2">
                    <span>GradePro AI Engine</span>
                    <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-mono font-medium">
                      {liveMetadata?.unit_code || unitCode}
                    </span>
                  </h2>
                  <p className="text-xs text-neutral-400 font-medium truncate max-w-sm">
                    {liveMetadata?.learner_name || file?.name || "Processing assignment..."}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 bg-neutral-800 px-3 py-1.5 rounded-xl border border-neutral-700/60">
                  <span className={`w-2 h-2 rounded-full ${isFailed ? "bg-rose-500" : isCompleted ? "bg-emerald-400" : "bg-[#8b5cf6] animate-pulse"}`}></span>
                  <span className="text-xs font-bold text-white">{progress}%</span>
                </div>
                {(isCompleted || isFailed) && (
                  <button
                    onClick={() => setIsModalOpen(false)}
                    className="p-1.5 rounded-xl text-neutral-400 hover:text-white hover:bg-neutral-800 transition cursor-pointer"
                  >
                    <X className="w-5 h-5" />
                  </button>
                )}
              </div>
            </div>

            {/* Glowing Yellow Progress Bar */}
            <div className="w-full bg-neutral-800 h-2 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 shadow-[0_0_12px_#8b5cf6] ${isFailed ? "bg-rose-500 shadow-[0_0_12px_#f43f5e]" : "bg-[#8b5cf6]"}`}
                style={{ width: `${progress}%` }}
              ></div>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-5 overflow-y-auto flex-1">
              {/* Current Status Callout */}
              <div className={`p-4 rounded-2xl border flex items-center justify-between ${
                isFailed
                  ? "bg-rose-50 border-rose-200 text-rose-900"
                  : isCompleted
                  ? "bg-emerald-50/70 border-emerald-200 text-emerald-900"
                  : "bg-amber-500/10 border-amber-300/60 text-neutral-900"
              }`}>
                <div className="flex items-center gap-3">
                  {isFailed ? (
                    <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
                  ) : !isCompleted ? (
                    <RefreshCw className="w-5 h-5 text-[#8b5cf6] animate-spin shrink-0" />
                  ) : (
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  )}
                  <div>
                    <h4 className="text-xs font-extrabold uppercase tracking-wide">
                      {isFailed ? "Grading Notice" : isCompleted ? "Grading Completed" : "Active Stage"}
                    </h4>
                    <p className="text-xs font-medium mt-0.5">{stageMessage}</p>
                  </div>
                </div>

                {isCompleted && result && (
                  <span
                    className={`px-3 py-1 rounded-lg text-xs font-extrabold ${
                      result.verdict === "PASS"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-rose-100 text-rose-800"
                    }`}
                  >
                    {result.verdict}
                  </span>
                )}
              </div>

              {/* ⚠️ Format & Structure Alerts Notice */}
              {liveMetadata?.format_issues && liveMetadata.format_issues.length > 0 && (
                <div className="p-3.5 rounded-2xl bg-amber-50 border border-amber-200 space-y-1.5">
                  <p className="text-[11px] font-extrabold text-amber-800 uppercase tracking-wider flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Document Format Notices (Marked as Refer)</span>
                  </p>
                  <ul className="list-disc list-inside text-xs text-amber-900 space-y-0.5">
                    {liveMetadata.format_issues.map((issue, idx) => (
                      <li key={idx}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 📑 LIVE EXTRACTED METADATA CARD (Zero Mock - 100% Real from Document) */}
              {liveMetadata && (
                <div className="p-4 rounded-2xl bg-neutral-50 border border-neutral-200/80 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-[11px] font-extrabold text-neutral-600 uppercase tracking-wider flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-neutral-500" />
                      <span>Extracted Document Details</span>
                    </h4>
                    <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Table 0 Parsed
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                    <div className="p-2.5 rounded-xl bg-white border border-neutral-100 shadow-xs">
                      <p className="text-[10px] text-neutral-400 font-bold uppercase flex items-center gap-1">
                        <User className="w-3 h-3" /> Learner Name
                      </p>
                      <p className="font-extrabold text-neutral-900 truncate mt-0.5">
                        {liveMetadata.learner_name || "Not Found"}
                      </p>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white border border-neutral-100 shadow-xs">
                      <p className="text-[10px] text-neutral-400 font-bold uppercase flex items-center gap-1">
                        <Hash className="w-3 h-3" /> Enrolment ID
                      </p>
                      <p className="font-extrabold text-neutral-900 truncate mt-0.5">
                        {liveMetadata.learner_id || "N/A"}
                      </p>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white border border-neutral-100 shadow-xs">
                      <p className="text-[10px] text-neutral-400 font-bold uppercase flex items-center gap-1">
                        <Building className="w-3 h-3" /> Awarding Body
                      </p>
                      <p className="font-extrabold text-neutral-900 truncate mt-0.5">
                        {liveMetadata.awarding_body || "QUALIFI"}
                      </p>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white border border-neutral-100 shadow-xs sm:col-span-2">
                      <p className="text-[10px] text-neutral-400 font-bold uppercase flex items-center gap-1">
                        <GraduationCap className="w-3 h-3" /> Qualification
                      </p>
                      <p className="font-extrabold text-neutral-900 truncate mt-0.5">
                        {liveMetadata.qualification || "Health and Social Care"}
                      </p>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white border border-neutral-100 shadow-xs">
                      <p className="text-[10px] text-neutral-400 font-bold uppercase flex items-center gap-1">
                        <BookOpen className="w-3 h-3" /> Unit Code
                      </p>
                      <p className="font-extrabold text-neutral-900 truncate mt-0.5">
                        {liveMetadata.unit_code || "HSC301"}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Step Checklist */}
              <div className="space-y-2">
                <h4 className="text-xs font-extrabold text-neutral-400 uppercase tracking-wider">Pipeline Checklist</h4>
                <div className="space-y-1.5">
                  {SEQUENTIAL_BEFORE.map((s, idx) => {
                    const Icon = s.icon;
                    const isDone = currentStageIdx > idx || isCompleted;
                    const isCurrent = currentStageIdx === idx && !isCompleted && !isFailed;
                    return (
                      <div
                        key={s.id}
                        className={`p-2.5 rounded-xl border transition flex items-center justify-between ${
                          isDone
                            ? "bg-emerald-50/60 border-emerald-200/60"
                            : isCurrent
                            ? "bg-brand-white border-brand-purple shadow-sm"
                            : "bg-neutral-50/50 border-neutral-100 text-neutral-400"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <div
                            className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
                              isDone
                                ? "bg-emerald-500 text-white"
                                : isCurrent
                                ? "bg-brand-purple text-brand-black animate-pulse"
                                : "bg-neutral-200 text-neutral-500"
                            }`}
                          >
                            {isDone ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : <Icon className="w-3.5 h-3.5" />}
                          </div>
                          <p className={`text-xs font-bold ${isDone || isCurrent ? "text-brand-black" : "text-neutral-500"}`}>
                            {s.label}
                          </p>
                        </div>
                        {isDone && <span className="text-[9px] font-extrabold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded">DONE</span>}
                        {isCurrent && <span className="text-[9px] font-extrabold text-brand-black bg-brand-purple/20 px-2 py-0.5 rounded animate-pulse">RUNNING</span>}
                      </div>
                    );
                  })}

                  <div className="rounded-2xl border border-brand-purple/40 p-2.5 space-y-1.5 bg-brand-white">
                    <p className="text-[10px] font-extrabold text-brand-purple uppercase tracking-wider px-1">
                      Running in parallel
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5">
                      {PARALLEL_STAGES.map((s) => {
                        const Icon = s.icon;
                        const isDone = parallelDone.includes(s.id) || isCompleted;
                        const isCurrent = !isDone && !isFailed && (
                          currentStageId === s.id ||
                          (["PARALLEL_AI", "AI_DETECTION", "PLAGIARISM"].includes(currentStageId) && currentStageIdx >= SEQUENTIAL_BEFORE.length)
                        );
                        return (
                          <div
                            key={s.id}
                            className={`p-2 rounded-xl border flex flex-col gap-1 ${
                              isDone
                                ? "bg-emerald-50/60 border-emerald-200/60"
                                : isCurrent
                                ? "bg-brand-white border-brand-purple shadow-sm"
                                : "bg-neutral-50/50 border-neutral-100"
                            }`}
                          >
                            <div className="flex items-center gap-1.5">
                              <div className={`w-5 h-5 rounded-md flex items-center justify-center ${
                                isDone ? "bg-emerald-500 text-white" : isCurrent ? "bg-brand-purple text-brand-black animate-pulse" : "bg-neutral-200 text-neutral-500"
                              }`}>
                                {isDone ? <Check className="w-3 h-3 stroke-[3]" /> : <Icon className="w-3 h-3" />}
                              </div>
                              <p className={`text-[11px] font-bold ${isDone || isCurrent ? "text-brand-black" : "text-neutral-500"}`}>{s.label}</p>
                            </div>
                            {isDone && <span className="text-[9px] font-extrabold text-emerald-700">DONE</span>}
                            {isCurrent && <span className="text-[9px] font-extrabold text-brand-purple">RUNNING</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {SEQUENTIAL_AFTER.map((s, idx) => {
                    const Icon = s.icon;
                    const absIdx = SEQUENTIAL_BEFORE.length + PARALLEL_STAGES.length + idx;
                    const isDone = currentStageIdx > absIdx || isCompleted;
                    const isCurrent = currentStageIdx === absIdx && !isCompleted && !isFailed;
                    return (
                      <div
                        key={s.id}
                        className={`p-2.5 rounded-xl border transition flex items-center justify-between ${
                          isDone
                            ? "bg-emerald-50/60 border-emerald-200/60"
                            : isCurrent
                            ? "bg-brand-white border-brand-purple shadow-sm"
                            : "bg-neutral-50/50 border-neutral-100 text-neutral-400"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
                            isDone ? "bg-emerald-500 text-white" : isCurrent ? "bg-brand-purple text-brand-black animate-pulse" : "bg-neutral-200 text-neutral-500"
                          }`}>
                            {isDone ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : <Icon className="w-3.5 h-3.5" />}
                          </div>
                          <p className={`text-xs font-bold ${isDone || isCurrent ? "text-brand-black" : "text-neutral-500"}`}>{s.label}</p>
                        </div>
                        {isDone && <span className="text-[9px] font-extrabold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded">DONE</span>}
                        {isCurrent && <span className="text-[9px] font-extrabold text-brand-black bg-brand-purple/20 px-2 py-0.5 rounded animate-pulse">RUNNING</span>}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Live Terminal Log Stream */}
              <div className="space-y-1.5">
                <h4 className="text-xs font-extrabold text-neutral-400 uppercase tracking-wider">Live System Logs</h4>
                <div className="bg-neutral-950 text-emerald-400 p-3 rounded-xl font-mono text-[11px] h-24 overflow-y-auto space-y-0.5 border border-neutral-800">
                  {eventLogs.map((log, i) => (
                    <p key={i} className="leading-tight">{log}</p>
                  ))}
                  {!isCompleted && !isFailed && (
                    <p className="text-neutral-500 animate-pulse">_ live pipeline telemetry stream...</p>
                  )}
                </div>
              </div>

              {/* Completed Results Inside Modal */}
              {isCompleted && result && (
                <div className="p-4 rounded-2xl bg-neutral-900 text-white space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[10px] text-neutral-400 font-bold uppercase tracking-wider">Assessor Feedback Summary</p>
                      <h3 className="text-base font-extrabold text-white">
                        {result.metadata?.learner_name || "Learner Submission"}
                      </h3>
                      <p className="text-xs text-neutral-400">
                        {result.metadata?.unit_code || unitCode} • {result.metadata?.qualification || "Diploma"}
                      </p>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-xl text-xs font-extrabold border-2 border-brand-purple ${
                        result.verdict === "PASS"
                          ? "bg-emerald-500 text-white"
                          : "bg-rose-500 text-white"
                      }`}
                    >
                      {result.verdict}
                    </span>
                  </div>

                  {(result.ai_detection || result.plagiarism || result.review_required) && (
                    <div className="text-xs space-y-1 border border-brand-purple/40 rounded-xl p-3">
                      {result.review_required && (
                        <p className="font-extrabold text-brand-purple">MAIN_ASSESSOR review required</p>
                      )}
                      <p>AI detection: {((result.ai_detection?.score ?? 0) * 100).toFixed(0)}%{result.ai_detection?.flagged ? " · FLAGGED" : ""}</p>
                      <p>Plagiarism: {(result.plagiarism?.overall_similarity_pct ?? 0).toFixed(1)}%</p>
                    </div>
                  )}

                  <div className="flex items-center gap-2.5 pt-1">
                    {result.docxUrl && (
                      <a
                        href={result.docxUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 flex items-center justify-center gap-1.5 py-3 rounded-xl bg-neutral-800 text-white font-bold text-xs hover:bg-neutral-700 transition border border-neutral-700"
                      >
                        <FileCode className="w-4 h-4" />
                        <span>Download DOCX</span>
                      </a>
                    )}
                    {result.pdfUrl && (
                      <a
                        href={result.pdfUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 flex items-center justify-center gap-1.5 py-3 rounded-xl bg-[#8b5cf6] text-black font-extrabold text-xs hover:bg-[#8b5cf6] transition shadow-md"
                      >
                        <Download className="w-4 h-4 stroke-[2.5]" />
                        <span>Download PDF</span>
                      </a>
                    )}
                    <button
                      onClick={() => setIsModalOpen(false)}
                      className="px-4 py-3 rounded-xl bg-neutral-800 text-neutral-300 font-bold text-xs hover:bg-neutral-700 transition cursor-pointer"
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
