export type Role = 'victim' | 'counsellor' | 'officer' | 'state' | 'national' | 'admin';

export type Consent = {
  id?: string;
  wellbeing: boolean;
  voice: boolean;
  language?: string;
  version?: string;
  erasure?: {
    voice_files_removed?: number;
    voice_sessions_redacted?: number;
    checkins_redacted?: number;
  };
};

export type User = {
  id: string;
  name: string;
  email: string;
  role: Role | string;
  district_id: string;
  state_id: string;
  consent: Consent | null;
  demo_enabled: boolean;
};

export type CaseSummary = {
  id: string;
  stage?: string;
  district?: string;
  district_id?: string;
  assigned_to?: string | null;
  priority?: string;
  scores?: Record<string, number> | null;
  trend?: { direction?: string };
  last_checkin?: string | null;
  case_type?: string;
  conditions?: Record<string, any>;
};

export type ChatReply = {
  message: string;
  suggest_safety_report?: boolean;
  method?: string;
  sent?: boolean;
  disclaimer?: string;
};

export type ResearchPayload = {
  mode?: string;
  metrics: Record<string, any>;
  prediction_distribution?: Record<string, number>;
  fallback_usage?: number;
  bias_evaluation?: Record<string, string>;
  limitation?: string;
  metrics_framing?: string;
};
