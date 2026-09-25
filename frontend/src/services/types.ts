export type Role = "employee" | "it_support" | "admin";
export type Priority = "low" | "medium" | "high" | "critical";

export interface User {
  id: number;
  email: string;
  username: string;
  full_name: string;
  role: Role;
  department: string | null;
  department_id: number | null;
  job_title: string | null;
  location: string | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Sla {
  target_minutes: number;
  elapsed_minutes: number;
  remaining_minutes: number;
  percent: number;
  breached: boolean;
  due_at: string;
}

export interface Ticket {
  id: number;
  ticket_number: string;
  title: string;
  description: string;
  category: string | null;
  category_id: number | null;
  sub_category: string | null;
  intent: string | null;
  entities: Record<string, string>;
  ai_confidence: number | null;
  classification_method: string | null;
  priority: Priority;
  user_priority: Priority | null;
  system_priority: Priority | null;
  priority_confidence: number | null;
  priority_reason: string | null;
  priority_impact: string | null;
  priority_urgency: string | null;
  status: string;
  source: string;
  is_open: boolean;
  creator: { id: number; name: string; department: string | null; job_title: string | null } | null;
  assignee: { id: number; name: string } | null;
  department: string | null;
  incident_id: number | null;
  duplicate_of_id: number | null;
  resolved_by_ai: boolean;
  resolution_summary: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  sla: Sla;
}

export interface Alert {
  type: "warning" | "info" | "success" | "incident" | "duplicate" | "approval" | "escalation" | "error";
  message: string;
}

export interface ProgressStep {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "skipped";
}

export interface SolutionCandidate {
  kind: "solution" | "kb_procedure" | "ai_grounded" | "ai_generated";
  label: string;
  title: string;
  summary: string;
  steps: string[];
  routing_level: string;
  confidence: number;
  solution_id: number | null;
  source_ticket: string | null;
  sources: string[];
  automated_actions: string[];
  similarity: number | null;
  model: string | null;
  safety_flags: string[];
}

export interface ActionView {
  id: number;
  tool: string;
  label: string;
  description: string;
  permission: "safe" | "restricted" | "dangerous";
  risk_note: string;
  status: string;
  approver_role: string | null;
  result: { ok?: boolean | null; summary?: string; mode?: string };
  created_at: string | null;
  ticket_id?: number;
  ticket_number?: string;
  ticket_title?: string;
  can_decide?: boolean;
}

export interface TicketCard {
  id: number;
  number: string;
  title: string;
  status: string;
  category: string | null;
  intent: string | null;
  sub_category: string | null;
  priority: Priority;
  user_priority: Priority | null;
  system_priority: Priority | null;
  confidence: number | null;
  department: string | null;
}

export interface PriorityAssessment {
  user_priority: Priority | null;
  system_priority: Priority;
  confidence: number;
  reason: string;
  impact: string;
  urgency: string;
  alert: string | null;
  method: string;
}

export interface ChatPayload {
  alerts?: Alert[];
  progress?: ProgressStep[];
  ticket?: TicketCard;
  solution?: SolutionCandidate;
  approvals?: ActionView[];
  escalation?: { department: string; reason: string; assignee: string | null };
  incident?: { number: string; title: string; status?: string; created?: boolean; reports?: number };
  duplicate?: { number: string; title: string; status: string; similarity: number };
  similar?: { number: string; title: string; status: string; similarity: number }[];
  agent?: { state: string; attempt: number; routing_level: string | null; run_id: number };
  priority_assessment?: PriorityAssessment;
  classification?: { category: string; intent: string | null; confidence: number; method: string; entities: Record<string, string> };
  quick_replies?: string[];
  draft?: { category: string | null };
  attachments?: { token: string; filename: string; content_type: string; size: number }[];
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "system" | "agent";
  content: string;
  payload: ChatPayload;
  is_internal: boolean;
  author: string | null;
  created_at: string;
  ticket_id: number | null;
}

export interface ChatReply {
  conversation_id: number;
  message: string;
  stage: string;
  payload: ChatPayload;
  quick_replies: string[];
  ticket_id: number | null;
  ticket_number: string | null;
  message_id: number | null;
}

export interface Incident {
  id: number;
  incident_number: string;
  title: string;
  description: string | null;
  category: string | null;
  priority: Priority | null;
  status: string;
  department: string | null;
  root_cause: string | null;
  resolution: string | null;
  detection_similarity: number | null;
  first_reported: string;
  last_reported: string;
  resolved_at: string | null;
  created_at: string;
  ticket_count: number | null;
}

export interface Solution {
  id: number;
  title: string;
  problem_description: string;
  symptoms: string | null;
  root_cause: string | null;
  solution_description: string;
  steps: string[];
  automated_actions: string[];
  confidence_level: string;
  source: string;
  category: string | null;
  category_id: number | null;
  intent: string | null;
  times_used: number;
  times_successful: number;
  times_failed: number;
  success_rate: number | null;
  is_active: boolean;
  rejected: boolean;
  ticket_id: number | null;
  ticket_number: string | null;
  created_at: string;
  verified_at: string | null;
  similarity?: number;
}

export interface KnowledgeDoc {
  id: number;
  title: string;
  doc_type: string;
  category: string | null;
  category_id: number | null;
  source: string;
  trust_level: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  excerpt: string;
  content?: string;
}

export interface NameCount { name: string; count: number; label?: string }
