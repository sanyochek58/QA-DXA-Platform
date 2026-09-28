// Типы ответов API. Совпадают со схемами Pydantic в services/core и services/ml.

export type Role = "technologist" | "radiologist" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  snils: string | null;
  esia_linked: boolean;
}

export interface EsiaConfig {
  enabled: boolean;
  mode: "off" | "mock" | "real";
}

export interface MockEsiaPerson {
  full_name: string;
  snils: string;
  email: string | null;
  phone: string | null;
}

export type StudyStatus = "processing" | "done" | "failed";
export type ReviewStatus = "not_required" | "pending" | "confirmed" | "corrected";
export type Region = "spine" | "right_hip" | "left_hip" | "unknown";

export interface UserShort {
  id: string;
  full_name: string;
}

export interface StudyListItem {
  id: string;
  created_at: string;
  title: string | null;
  n_images: number;
  status: StudyStatus;
  quality_ok: boolean | null;
  needs_review: boolean;
  violation_codes: string[];
  review_status: ReviewStatus;
  review_quality_ok: boolean | null;
  uploaded_by: UserShort;
}

export interface Violation {
  code: string;
  region: Region;
  severity: "critical" | "minor";
  probability: number;
  threshold: number;
  title_ru: string;
  message_ru: string;
  how_to_fix_ru: string;
  evidence: Record<string, number>;
  image_indexes: number[];
}

export interface RegionResult {
  region: Region;
  quality_ok: boolean;
  probability_bad: number;
  threshold: number;
  image_indexes: number[];
}

export interface ImageResult {
  index: number;
  file: string;
  region: Region;
  region_confidence: number;
  preview_path: string | null;
  measurements: Record<string, number>;
}

export interface AnalyzeResult {
  study_id: string;
  quality_ok: boolean;
  needs_review: boolean;
  review_reasons: string[];
  regions: RegionResult[];
  violations: Violation[];
  images: ImageResult[];
  metadata: Record<string, string>;
  model_version: string;
  processing_ms: number;
}

export interface Study extends StudyListItem {
  error: string | null;
  result: AnalyzeResult | null;
  model_version: string | null;
  processing_ms: number | null;
  finished_at: string | null;
  file_names: string[];
  reviewed_by: UserShort | null;
  reviewed_at: string | null;
  review_comment: string | null;
}

export interface StudyPage {
  items: StudyListItem[];
  total: number;
}

export interface Summary {
  days: number;
  total: number;
  done: number;
  failed: number;
  processing: number;
  quality_ok: number;
  quality_bad: number;
  bad_rate: number;
  review_pending: number;
  reviewed: number;
  review_agreement: number | null;
  avg_processing_ms: number | null;
  by_day: { day: string; total: number; bad: number }[];
  by_code: { code: string; count: number }[];
  by_operator: { user_id: string; full_name: string; total: number; bad: number; bad_rate: number }[];
}

export interface SystemStatus {
  core: string;
  database: string;
  ml: string;
}

export interface TargetMetrics {
  roc_auc: number;
  pr_auc: number;
  f1: number;
  precision: number;
  recall: number;
  balanced_accuracy: number;
  positives: number;
  n: number;
  threshold: number;
  model: string;
}

export interface ModelInfo {
  version: string | null;
  metrics: {
    trained_at: string;
    n_images: number;
    n_studies: number;
    targets: Record<string, TargetMetrics>;
    study_level?: {
      n: number;
      bad_studies: number;
      accuracy: number;
      recall_bad: number;
      precision_bad: number;
      specificity: number;
      balanced_accuracy: number;
    };
  } | null;
}
