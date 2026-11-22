export interface SessionConfig {
  token: string;
  lanUrl: string;
  publicUrl: string;
  activeUrl: string;
  requireBiometric: boolean;
}

export interface TelemetrySnapshot {
  ok: boolean;
  ip_locale?: string;
  port?: number;
  url_publique?: string;
  tunnel_distant?: boolean;
  cpu_pct: number;
  ram_pct: number;
  disque_libre_go: number;
  llm_provider?: string;
  llm_modele?: string;
  budget_jour?: number;
  plafond_jour?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  toolSteps?: string[];
}

export interface TerminalEntry {
  id: string;
  commande: string;
  sortie: string;
  needsConfirm: boolean;
  timestamp: number;
}

export interface PairingPayload {
  code: string;
  lanUrl: string;
  publicUrl: string;
}

export interface ApiAuthResponse {
  ok: boolean;
  token?: string;
  lan_url?: string;
  public_url?: string;
  message?: string;
}

export interface WsServerEvent {
  type: string;
  message?: string;
  texte?: string;
  erreur?: string;
  nom?: string;
  extrait?: string;
  cpu_pct?: number;
  ram_pct?: number;
  disque_libre_go?: number;
  commande?: string;
  sortie?: string;
}
