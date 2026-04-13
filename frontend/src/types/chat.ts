/** 与后端 Pydantic ``Citation`` / ``EvidenceEntry`` 序列化字段对齐 */

/** Orchestrator 派生的子智能体运行态（与 ``OPENAGENT_ARCHITECTURE.md`` WS 事件对齐，payload 可扩展） */
export type SubAgentStatus = "running" | "completed" | "failed";

export interface SubAgentRun {
  agent_id: string;
  profile_id?: string;
  task_summary?: string;
  status: SubAgentStatus;
  lastProgress?: string;
  outputSummary?: string;
  errorMessage?: string;
}

export interface CitationDTO {
  chunk_id: string;
  version_id: string;
  source_span: Record<string, unknown>;
  location_summary: string;
}

export interface EvidenceEntryDTO {
  chunk_id: string;
  version_id: string;
  origin_type: string;
  location_summary: string;
  evidence_snippet_text_v1?: string | null;
  evidence_entry_tokens_v1?: number | null;
  dense_score?: number | null;
  keyword_score?: number | null;
  rerank_score?: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  citations?: CitationDTO[];
  evidenceEntries?: EvidenceEntryDTO[];
}
