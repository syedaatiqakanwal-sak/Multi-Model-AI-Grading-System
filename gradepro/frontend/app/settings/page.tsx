"use client";

import { useState, useEffect } from "react";
import {
  Key,
  Server,
  Sliders,
  Plus,
  KeyRound,
  Trash2,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  Zap,
  RefreshCw,
  X,
  Sparkles,
  Upload,
  FileCheck,
  Check,
  Building2,
  GraduationCap,
  BookOpen,
  FileText,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { api } from "@/lib/api";

interface ApiKeyItem {
  id: string;
  name: string;
  provider: "OpenAI" | "Anthropic" | "Gemini" | "Groq" | "DeepSeek" | "Custom";
  model: string;
  key: string;
  dailyLimit: number;
  active: boolean;
  createdAt: string;
}

interface UnitRubricItem {
  id: string;
  unit_code: string;
  unit_name: string;
  qualification: string;
  awarding_body: string;
  word_count_min: number;
  word_count_max: number;
  criteria_count: number;
  active: boolean;
  filename: string;
  created_at: string;
}

const DEFAULT_MODELS: Record<string, string> = {
  OpenAI: "gpt-4o",
  Anthropic: "claude-3-5-sonnet-20241022",
  Gemini: "gemini-1.5-pro",
  Groq: "llama-3.3-70b-versatile",
  DeepSeek: "deepseek-chat",
  Custom: "gpt-4o",
};

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"rubrics" | "api" | "ollama" | "format">("rubrics");

  // API Key Rotation State
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [showAddKeyForm, setShowAddKeyForm] = useState(false);
  const [showKeyText, setShowKeyText] = useState(false);
  const [testingKeyId, setTestingKeyId] = useState<string | null>(null);
  const [keyTestResult, setKeyTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null);

  const [formProvider, setFormProvider] = useState<ApiKeyItem["provider"]>("Groq");
  const [formName, setFormName] = useState("");
  const [formKey, setFormKey] = useState("");
  const [formModel, setFormModel] = useState(DEFAULT_MODELS["Groq"]);
  const [formLimit, setFormLimit] = useState(1000);

  // Unit Rubrics State
  const [unitRubrics, setUnitRubrics] = useState<UnitRubricItem[]>([
    {
      id: "hsc301-rubric",
      unit_code: "HSC301",
      unit_name: "An Introduction to Health and Social Care",
      qualification: "QUALIFI Level 3 Diploma in Health and Social Care",
      awarding_body: "QUALIFI",
      word_count_min: 1850,
      word_count_max: 2150,
      criteria_count: 7,
      active: true,
      filename: "HSC301_rubric.json",
      created_at: "20 Aug 2026",
    },
  ]);
  const [showAddRubricForm, setShowAddRubricForm] = useState(false);
  const [rubricFile, setRubricFile] = useState<File | null>(null);
  const [rubricUnitCode, setRubricUnitCode] = useState("");
  const [expandedRubricCode, setExpandedRubricCode] = useState<string | null>(null);
  const [expandedRubricData, setExpandedRubricData] = useState<any | null>(null);
  const [loadingRubricDetail, setLoadingRubricDetail] = useState(false);

  // Load saved data on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const res = await api.get("/v1/settings/keys");
        if (res.data?.keys && res.data.keys.length > 0) {
          setKeys(res.data.keys);
        } else {
          const saved = localStorage.getItem("gradepro_api_keys");
          if (saved) setKeys(JSON.parse(saved));
        }
      } catch (e) {
        const saved = localStorage.getItem("gradepro_api_keys");
        if (saved) setKeys(JSON.parse(saved));
      }

      try {
        const resRubrics = await api.get("/v1/rubrics");
        if (resRubrics.data?.rubrics && resRubrics.data.rubrics.length > 0) {
          setUnitRubrics(resRubrics.data.rubrics);
        }
      } catch (e) {}
    };
    loadData();
  }, []);

  const syncKeys = async (newKeys: ApiKeyItem[]) => {
    setKeys(newKeys);
    localStorage.setItem("gradepro_api_keys", JSON.stringify(newKeys));
    try {
      await api.post("/v1/settings/keys", { keys: newKeys });
    } catch (e) {}
  };

  const handleAddKey = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formKey.trim()) return;

    const newKey: ApiKeyItem = {
      id: "key-" + Date.now(),
      name: formName.trim() || `${formProvider} Primary Key`,
      provider: formProvider,
      model: formModel || DEFAULT_MODELS[formProvider],
      key: formKey.trim(),
      dailyLimit: Number(formLimit) || 1000,
      active: true,
      createdAt: new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
    };

    const updated = [newKey, ...keys];
    syncKeys(updated);

    setShowAddKeyForm(false);
    setFormName("");
    setFormKey("");
    setFormLimit(1000);
  };

  const toggleKeyActive = (id: string) => {
    const updated = keys.map((k) => (k.id === id ? { ...k, active: !k.active } : k));
    syncKeys(updated);
  };

  const deleteKey = (id: string) => {
    const updated = keys.filter((k) => k.id !== id);
    syncKeys(updated);
  };

  const handleTestKey = async (keyItem: ApiKeyItem) => {
    setTestingKeyId(keyItem.id);
    setKeyTestResult(null);

    try {
      const res = await api.post("/v1/settings/keys/test", {
        provider: keyItem.provider,
        api_key: keyItem.key,
        model_name: keyItem.model,
      });

      setTestingKeyId(null);
      setKeyTestResult({
        id: keyItem.id,
        success: res.data?.success === true,
        message: res.data?.message || "Connection successful (200 OK)",
      });
    } catch (e: any) {
      setTestingKeyId(null);
      setKeyTestResult({
        id: keyItem.id,
        success: false,
        message: e?.response?.data?.detail || e?.message || "Failed to connect to provider.",
      });
    }
  };

  const handleUploadRubric = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rubricFile) return;

    const formData = new FormData();
    formData.append("rubric_file", rubricFile);
    if (rubricUnitCode.trim()) {
      formData.append("unit_code", rubricUnitCode.toUpperCase().trim());
    }

    try {
      const res = await api.post("/v1/rubrics/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const saved: UnitRubricItem = res.data.rubric;
      const updated = [saved, ...unitRubrics.filter((r) => r.unit_code !== saved.unit_code)];
      setUnitRubrics(updated);
      setShowAddRubricForm(false);
      setRubricFile(null);
      setRubricUnitCode("");
    } catch (e: any) {
      alert(`Upload failed: ${e?.response?.data?.detail || e?.message || "Unknown error"}`);
    }
  };

  const handleViewRubricDetail = async (unitCode: string) => {
    if (expandedRubricCode === unitCode) {
      setExpandedRubricCode(null);
      setExpandedRubricData(null);
      return;
    }

    setExpandedRubricCode(unitCode);
    setLoadingRubricDetail(true);
    try {
      const res = await api.get(`/v1/rubrics/${unitCode}`);
      setExpandedRubricData(res.data);
    } catch (e) {
      setExpandedRubricData(null);
    } finally {
      setLoadingRubricDetail(false);
    }
  };

  const activeKeysCount = keys.filter((k) => k.active).length;
  const activeRubricsCount = unitRubrics.filter((r) => r.active).length;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">Settings & Configuration</h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Manage unit assignment rubrics, reasoning API keys (Groq/OpenAI/Claude), and formatting rules.
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex flex-wrap items-center gap-2 border-b border-neutral-200 pb-2">
          <button
            type="button"
            onClick={() => setActiveTab("rubrics")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "rubrics" ? "bg-[#8b5cf6] text-black shadow-sm" : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span>Official Assignment Rubrics ({activeRubricsCount} Active Units)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("api")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "api" ? "bg-[#8b5cf6] text-black shadow-sm" : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <Key className="w-4 h-4" />
            <span>API Key Rotation ({activeKeysCount} Active)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("ollama")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "ollama" ? "bg-[#8b5cf6] text-black shadow-sm" : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <Server className="w-4 h-4" />
            <span>Ollama Local Model</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("format")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "format" ? "bg-[#8b5cf6] text-black shadow-sm" : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>College Format Rules</span>
          </button>
        </div>

        {/* 1. Official Assignment Rubrics Tab */}
        {activeTab === "rubrics" && (
          <div className="space-y-5">
            <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-neutral-900">Official Unit Rubrics & Assessment Specifications</h3>
                  <p className="text-xs text-neutral-500 font-medium mt-0.5">
                    Upload official rubric JSON files defining learning outcomes, criteria, word count ranges, and key topics for any unit.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddRubricForm(!showAddRubricForm)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#8b5cf6] text-black text-xs font-extrabold hover:bg-[#8b5cf6] transition shadow-sm cursor-pointer"
                >
                  <Plus className="w-4 h-4 stroke-[2.5]" />
                  <span>{showAddRubricForm ? "Close Form" : "+ Upload Unit Rubric JSON"}</span>
                </button>
              </div>

              {/* Upload Rubric Form */}
              {showAddRubricForm && (
                <div className="p-6 rounded-2xl bg-neutral-50 border border-neutral-200/80 space-y-4 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between pb-2 border-b border-neutral-200">
                    <h4 className="text-xs font-extrabold text-neutral-900 uppercase tracking-wide flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-[#8b5cf6]" />
                      <span>Upload Official Unit Rubric JSON</span>
                    </h4>
                    <button type="button" onClick={() => setShowAddRubricForm(false)} className="text-neutral-400 hover:text-black">
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <form onSubmit={handleUploadRubric} className="space-y-4">
                    <div>
                      <label className="text-xs font-bold text-neutral-700 block mb-1">
                        Select Rubric JSON File (*.json)
                      </label>
                      <div className="border border-dashed border-neutral-300 rounded-xl p-4 flex items-center justify-between bg-white">
                        <input
                          type="file"
                          id="rubric-upload-input"
                          accept=".json"
                          className="hidden"
                          onChange={(e) => e.target.files?.[0] && setRubricFile(e.target.files[0])}
                          required
                        />
                        <label htmlFor="rubric-upload-input" className="flex items-center gap-3 cursor-pointer text-xs font-medium text-neutral-700">
                          <Upload className="w-5 h-5 text-[#8b5cf6]" />
                          <span>{rubricFile ? rubricFile.name : "Choose JSON file (e.g. HSC301_rubric.json, BUS301_rubric.json)"}</span>
                        </label>
                        {rubricFile && (
                          <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                            {Math.round(rubricFile.size / 1024)} KB
                          </span>
                        )}
                      </div>
                    </div>

                    <div>
                      <label className="text-xs font-bold text-neutral-700 block mb-1">
                        Unit Code Override (Optional)
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. HSC301 (will auto-detect from JSON if left blank)"
                        value={rubricUnitCode}
                        onChange={(e) => setRubricUnitCode(e.target.value)}
                        className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                      />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowAddRubricForm(false)}
                        className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-100 transition"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-5 py-2 rounded-xl bg-[#8b5cf6] text-black text-xs font-extrabold hover:bg-[#8b5cf6] transition shadow-sm"
                      >
                        Upload & Activate Rubric
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Rubric Cards List */}
              <div className="grid grid-cols-1 gap-4">
                {unitRubrics.map((r) => (
                  <div
                    key={r.id}
                    className="p-5 rounded-2xl border border-neutral-200/80 bg-white hover:border-[#8b5cf6]/60 transition shadow-sm space-y-4"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex items-start gap-3.5">
                        <div className="w-11 h-11 rounded-xl bg-[#8b5cf6]/20 text-black flex items-center justify-center font-extrabold text-xs shrink-0">
                          {r.unit_code.slice(0, 3)}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-extrabold text-neutral-900">{r.unit_code}</h4>
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-neutral-100 text-neutral-600 rounded">
                              {r.awarding_body}
                            </span>
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded flex items-center gap-1">
                              <Check className="w-3 h-3" /> Active Standard
                            </span>
                          </div>
                          <p className="text-xs font-semibold text-neutral-700 mt-0.5">{r.unit_name}</p>
                          <p className="text-[11px] text-neutral-400 font-medium">{r.qualification}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 self-end sm:self-center">
                        <div className="text-right">
                          <p className="text-xs font-bold text-neutral-900">
                            {r.word_count_min.toLocaleString()} – {r.word_count_max.toLocaleString()} words
                          </p>
                          <p className="text-[11px] text-neutral-400 font-medium">{r.criteria_count} assessment criteria</p>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleViewRubricDetail(r.unit_code)}
                          className="px-3 py-1.5 rounded-lg border border-neutral-200 text-xs font-bold text-neutral-700 hover:bg-neutral-50 transition flex items-center gap-1.5"
                        >
                          <span>{expandedRubricCode === r.unit_code ? "Hide Details" : "View Criteria"}</span>
                          {expandedRubricCode === r.unit_code ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Expanded Criteria Inspector */}
                    {expandedRubricCode === r.unit_code && (
                      <div className="pt-3 border-t border-neutral-100 space-y-3 animate-in fade-in duration-150">
                        {loadingRubricDetail ? (
                          <div className="p-4 text-center text-xs text-neutral-400 font-medium flex items-center justify-center gap-2">
                            <RefreshCw className="w-4 h-4 animate-spin text-[#8b5cf6]" />
                            <span>Loading rubric criteria specification...</span>
                          </div>
                        ) : expandedRubricData ? (
                          <div className="space-y-3">
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] bg-neutral-50 p-3 rounded-xl">
                              <div>
                                <span className="font-bold text-neutral-500">Referencing:</span>{" "}
                                <span className="font-semibold text-neutral-800">
                                  {expandedRubricData.referencing_requirements?.style || "Harvard Style"}
                                </span>
                              </div>
                              <div>
                                <span className="font-bold text-neutral-500">In-Text Citations:</span>{" "}
                                <span className="font-semibold text-neutral-800">Mandatory per criterion</span>
                              </div>
                              <div>
                                <span className="font-bold text-neutral-500">Bibliography:</span>{" "}
                                <span className="font-semibold text-neutral-800">Required at end of submission</span>
                              </div>
                            </div>

                            <div className="space-y-2">
                              {expandedRubricData.learning_outcomes?.map((lo: any, lIdx: number) => (
                                <div key={lIdx} className="p-3 rounded-xl border border-neutral-200/60 bg-white space-y-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-extrabold bg-[#8b5cf6] text-black px-1.5 py-0.5 rounded">
                                      {lo.id}
                                    </span>
                                    <h5 className="text-xs font-bold text-neutral-900">{lo.title}</h5>
                                  </div>
                                  <div className="space-y-1.5 pl-2">
                                    {lo.criteria?.map((c: any, cIdx: number) => (
                                      <div key={cIdx} className="text-[11px] text-neutral-700 flex items-start gap-2">
                                        <span className="font-mono font-bold text-neutral-500 shrink-0">{c.id}</span>
                                        <div>
                                          <p className="font-medium text-neutral-800">{c.description}</p>
                                          {c.key_topics && (
                                            <p className="text-[10px] text-neutral-400 font-medium mt-0.5">
                                              Key concepts: {c.key_topics.join(", ")}
                                            </p>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-neutral-400 font-medium">Could not load criteria details.</p>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 2. API Key Rotation Tab */}
        {activeTab === "api" && (
          <div className="space-y-5">
            <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-neutral-900">API Key Rotation Pool</h3>
                  <p className="text-xs text-neutral-500 font-medium mt-0.5">
                    Configure API keys for Groq, OpenAI, Anthropic, or Gemini. The pipeline rotates active keys atomically with zero-temperature deterministic execution.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddKeyForm(!showAddKeyForm)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#8b5cf6] text-black text-xs font-extrabold hover:bg-[#8b5cf6] transition shadow-sm cursor-pointer"
                >
                  <Plus className="w-4 h-4 stroke-[2.5]" />
                  <span>{showAddKeyForm ? "Close Form" : "+ Add API Key"}</span>
                </button>
              </div>

              {/* Add Key Form */}
              {showAddKeyForm && (
                <div className="p-6 rounded-2xl bg-neutral-50 border border-neutral-200/80 space-y-4 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between pb-2 border-b border-neutral-200">
                    <h4 className="text-xs font-extrabold text-neutral-900 uppercase tracking-wide flex items-center gap-2">
                      <KeyRound className="w-4 h-4 text-[#8b5cf6]" />
                      <span>Add Provider API Key</span>
                    </h4>
                    <button type="button" onClick={() => setShowAddKeyForm(false)} className="text-neutral-400 hover:text-black">
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <form onSubmit={handleAddKey} className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs font-bold text-neutral-700 block mb-1">Provider</label>
                        <select
                          value={formProvider}
                          onChange={(e) => {
                            const p = e.target.value as ApiKeyItem["provider"];
                            setFormProvider(p);
                            setFormModel(DEFAULT_MODELS[p]);
                          }}
                          className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                        >
                          <option value="Groq">Groq (Ultra-Fast OSS Models)</option>
                          <option value="OpenAI">OpenAI (GPT-4o, GPT-4o-mini)</option>
                          <option value="Anthropic">Anthropic Claude (Claude 3.5)</option>
                          <option value="Gemini">Google Gemini (Gemini 1.5/2.0 Flash/Pro)</option>
                          <option value="DeepSeek">DeepSeek (DeepSeek-Chat)</option>
                          <option value="Custom">Custom OpenAI-Compatible</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-xs font-bold text-neutral-700 block mb-1">Key Label / Name</label>
                        <input
                          type="text"
                          placeholder="e.g. Groq Production Llama 3.3"
                          value={formName}
                          onChange={(e) => setFormName(e.target.value)}
                          className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-medium text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs font-bold text-neutral-700 block mb-1">Model Name</label>
                        <input
                          type="text"
                          value={formModel}
                          onChange={(e) => setFormModel(e.target.value)}
                          required
                          className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-bold text-neutral-700 block mb-1">Daily Request Limit</label>
                        <input
                          type="number"
                          value={formLimit}
                          onChange={(e) => setFormLimit(Number(e.target.value))}
                          className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-xs font-bold text-neutral-700 block mb-1">API Secret Key</label>
                      <div className="relative">
                        <input
                          type={showKeyText ? "text" : "password"}
                          placeholder="gsk-... or sk-..."
                          value={formKey}
                          onChange={(e) => setFormKey(e.target.value)}
                          required
                          className="w-full p-2.5 pr-10 rounded-xl border border-neutral-200 text-xs font-mono text-neutral-900 outline-none bg-white focus:border-[#8b5cf6]"
                        />
                        <button
                          type="button"
                          onClick={() => setShowKeyText(!showKeyText)}
                          className="absolute right-3 top-2.5 text-neutral-400 hover:text-neutral-700"
                        >
                          {showKeyText ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowAddKeyForm(false)}
                        className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-100 transition"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-5 py-2 rounded-xl bg-[#8b5cf6] text-black text-xs font-extrabold hover:bg-[#8b5cf6] transition shadow-sm"
                      >
                        Save Key to Rotation Pool
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Keys List */}
              <div className="space-y-3">
                {keys.map((k) => (
                  <div
                    key={k.id}
                    className={`p-4 rounded-2xl border transition flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                      k.active ? "bg-white border-neutral-200 shadow-sm" : "bg-neutral-50/70 border-neutral-200/50 opacity-70"
                    }`}
                  >
                    <div className="flex items-center gap-3.5">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center font-extrabold text-xs shrink-0 ${
                          k.provider === "OpenAI"
                            ? "bg-emerald-100 text-emerald-800"
                            : k.provider === "Anthropic"
                            ? "bg-amber-100 text-amber-900"
                            : k.provider === "Gemini"
                            ? "bg-blue-100 text-blue-800"
                            : k.provider === "Groq"
                            ? "bg-orange-100 text-orange-800"
                            : "bg-purple-100 text-purple-800"
                        }`}
                      >
                        {k.provider.slice(0, 2).toUpperCase()}
                      </div>

                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-xs font-bold text-neutral-900">{k.name}</h4>
                          <span className="text-[10px] font-semibold text-neutral-500 bg-neutral-100 px-2 py-0.5 rounded">
                            {k.model}
                          </span>
                        </div>
                        <p className="text-[11px] text-neutral-400 font-mono mt-0.5">
                          {k.key.slice(0, 6)}••••••••{k.key.slice(-4)} • Added {k.createdAt}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={k.active}
                          onChange={() => toggleKeyActive(k.id)}
                          className="hidden"
                        />
                        <div
                          className={`w-9 h-5 rounded-full p-0.5 transition-colors ${
                            k.active ? "bg-[#8b5cf6]" : "bg-neutral-300"
                          }`}
                        >
                          <div
                            className={`w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
                              k.active ? "translate-x-4" : "translate-x-0"
                            }`}
                          ></div>
                        </div>
                        <span className="text-xs font-semibold text-neutral-700 w-14">
                          {k.active ? "Active" : "Paused"}
                        </span>
                      </label>

                      <button
                        type="button"
                        onClick={() => handleTestKey(k)}
                        disabled={testingKeyId === k.id}
                        className="px-2.5 py-1.5 rounded-lg border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition flex items-center gap-1"
                      >
                        {testingKeyId === k.id ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                        )}
                        <span>Test</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => deleteKey(k.id)}
                        className="p-1.5 rounded-lg text-neutral-400 hover:text-rose-600 hover:bg-rose-50 transition"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}

                {keyTestResult && (
                  <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span>{keyTestResult.message}</span>
                    </div>
                    <button type="button" onClick={() => setKeyTestResult(null)} className="text-emerald-700 hover:text-emerald-900">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 3. Ollama Tab */}
        {activeTab === "ollama" && (
          <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-neutral-900">Local Ollama Configuration</h3>
            <p className="text-xs text-neutral-500 font-medium">
              Run offline or zero-cloud inference using local GGUF models as primary or backup reasoning models.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="text-xs font-bold text-neutral-700 block mb-1">Ollama Endpoint</label>
                <input
                  type="text"
                  defaultValue="http://host.docker.internal:11434"
                  className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-900 outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-neutral-700 block mb-1">Model Name</label>
                <input
                  type="text"
                  defaultValue="llama3.3:70b"
                  className="w-full p-2.5 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-900 outline-none"
                />
              </div>
            </div>
          </div>
        )}

        {/* 4. Format Rules Tab */}
        {activeTab === "format" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-neutral-900">UKPDA Format Rules</h3>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">Active</span>
              </div>
              <div className="space-y-2 text-xs font-medium text-neutral-700 bg-neutral-50 p-3.5 rounded-xl">
                <p>• Body Font: Times New Roman (12pt)</p>
                <p>• Section Headings: 13pt Bold</p>
                <p>• Required: Introduction, Tasks, Conclusion, Bibliography</p>
                <p>• In-Text Citations: Harvard format required per criterion</p>
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-neutral-900">ILC Format Rules</h3>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">Active</span>
              </div>
              <div className="space-y-2 text-xs font-medium text-neutral-700 bg-neutral-50 p-3.5 rounded-xl">
                <p>• Body Font: Times New Roman (12pt)</p>
                <p>• Section Headings: 14pt Bold</p>
                <p>• Required: Introduction, Tasks, Conclusion, Bibliography</p>
                <p>• In-Text Citations: Harvard format required</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
