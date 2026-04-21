// Frontend API client — all calls go through the Next.js proxy which handles auth
const BASE = "/api/proxy";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function requestBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
  const filename = match?.[1] ?? "export.xlsx";
  const blob = await res.blob();
  return { blob, filename };
}

// ── Processes ──

export type Process = {
  id: number;
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  current_stage: string | null;
  period_year: number;
  period_month: number;
  acquirers: string[];
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ProcessConfig = {
  kushki_sftp_enabled: boolean;
};

export type ProcessLog = {
  id: number;
  level: "info" | "warning" | "error";
  stage: string;
  message: string;
  created_at: string;
};

export type ProgressData = {
  status: string;
  current_stage: string | null;
  progress: number;
  logs: ProcessLog[];
};

export const processApi = {
  list: () => request<Process[]>("/processes/"),
  config: () => request<ProcessConfig>("/processes/config"),
  get: (id: number) => request<Process>(`/processes/${id}`),
  create: (data: { name: string; period_year: number; period_month: number; acquirers: string[] }) =>
    request<Process>("/processes/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  run: (id: number) =>
    request<{ message: string }>(`/processes/${id}/run`, { method: "POST" }),
  progress: (id: number) => request<ProgressData>(`/processes/${id}/progress`),
  delete: (id: number) => request<void>(`/processes/${id}`, { method: "DELETE" }),
};

// ── Files ──

export type UploadedFile = {
  id: number;
  original_name: string;
  file_type: string;
  file_size: number;
  status: string;
};

export const filesApi = {
  list: (processId: number) => request<UploadedFile[]>(`/files/${processId}`),
  upload: async (processId: number, fileType: string, file: File) => {
    const formData = new FormData();
    formData.append("file_type", fileType);
    formData.append("file", file);
    return request<UploadedFile>(`/files/upload/${processId}`, {
      method: "POST",
      body: formData,
    });
  },
  delete: (fileId: number) => request<void>(`/files/${fileId}`, { method: "DELETE" }),
};

// ── Results ──

export type MerchantSummary = {
  merchant_id: string;
  merchant_name: string;
  tx_count: number;
  gross_amount: number;
  total_fee: number;
};

export type FeesResult = {
  total_fees: number;
  merchant_summary: MerchantSummary[];
  daily_breakdown: unknown[];
  withdrawals_summary: unknown;
  refunds_summary: unknown;
  other_fees_summary: unknown;
};

export type KushkiDay = {
  date: string;
  tx_count: number;
  gross_amount: number;
  commission: number;
  rolling_reserve: number;
  net_deposit: number;
};

export type KushkiResult = {
  total_net_deposit: number;
  daily_summary: KushkiDay[];
  merchant_detail: unknown[];
};

export type BanregioMovement = {
  date: string;
  description: string;
  debit: number;
  credit: number;
  deposit_ref: number;
};

export type BanregioResult = {
  summary: { total_credits: number; total_debits: number };
  movements: BanregioMovement[];
};

export type ConciliationMatch = {
  date: string;
  kushki_amount: number;
  banregio_amount: number;
  difference: number;
};

export type ConciliationRecord = {
  id: number;
  conciliation_type: "fees" | "kushki_daily" | "kushki_vs_banregio";
  total_conciliated: number;
  total_difference: number;
  matched: ConciliationMatch[];
  differences: ConciliationMatch[];
  unmatched_kushki: unknown[];
  unmatched_banregio: unknown[];
};

export const resultsApi = {
  fees: (processId: number) => request<FeesResult>(`/results/${processId}/fees`),
  kushki: (processId: number) => request<KushkiResult>(`/results/${processId}/kushki`),
  banregio: (processId: number) => request<BanregioResult>(`/results/${processId}/banregio`),
  conciliation: (processId: number) =>
    request<ConciliationRecord[]>(`/results/${processId}/conciliation`),
  exportFees: (processId: number) => requestBlob(`/results/${processId}/export/fees`),
  exportKushki: (processId: number) => requestBlob(`/results/${processId}/export/kushki`),
  exportBanregio: (processId: number) => requestBlob(`/results/${processId}/export/banregio`),
};

// ── Helpers ──

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function formatMoney(value: number | string | null | undefined): string {
  return Number(value || 0).toLocaleString("es-MX", { minimumFractionDigits: 2 });
}

export const MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

export const ACQUIRER_COLORS: Record<string, string> = {
  OXXOPay: "#f59e0b",
  Bitso: "#10b981",
  Kushki: "#375DFB",
  STP: "#8b5cf6",
};

export const STAGES = [
  "extracting_transactions",
  "extracting_withdrawals",
  "extracting_refunds",
  "processing_fees",
  "parsing_kushki",
  "parsing_banregio",
  "conciliating",
  "done",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  extracting_transactions: "Extrayendo transacciones",
  extracting_withdrawals: "Extrayendo retiros",
  extracting_refunds: "Extrayendo reembolsos",
  processing_fees: "Procesando FEES",
  parsing_kushki: "Parseando Kushki",
  parsing_banregio: "Parseando Banregio",
  conciliating: "Conciliando",
  done: "Completado",
};
