import type { ApiAuthResponse, PairingPayload, SessionConfig, TelemetrySnapshot } from "../types/riot";

export function normalizeBaseUrl(raw: string): string {
  const cleaned = raw.trim().replace(/\/+$/, "");
  if (!cleaned) return "";
  if (/^https?:\/\//i.test(cleaned)) return cleaned;
  return `http://${cleaned}`;
}

export function parsePairingQr(raw: string): PairingPayload | null {
  const text = raw.trim();
  if (!text) return null;
  try {
    if (text.startsWith("riot://")) {
      const url = new URL(text);
      const code = url.searchParams.get("code") || "";
      const lanUrl = normalizeBaseUrl(url.searchParams.get("lan") || "");
      const publicUrl = normalizeBaseUrl(url.searchParams.get("pub") || "");
      if (!code || (!lanUrl && !publicUrl)) return null;
      return { code, lanUrl, publicUrl };
    }
  } catch {
    return null;
  }
  return null;
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = 4500): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function resolveReachableUrl(lanUrl: string, publicUrl: string, token?: string): Promise<string> {
  const candidates = [normalizeBaseUrl(lanUrl), normalizeBaseUrl(publicUrl)].filter(Boolean);
  if (candidates.length === 0) {
    throw new Error("Aucune adresse serveur configurée.");
  }
  const headers: Record<string, string> = token ? { "x-keranos-token": token } : {};
  for (const base of candidates) {
    try {
      const target = token ? `${base}/api/mobile/telemetry` : `${base}/api/version`;
      const res = await fetchWithTimeout(target, { method: "GET", headers }, 1800);
      if (res.ok || res.status === 401) {
        return base;
      }
    } catch {
      // Tente l'URL suivante (ex: bascule LAN -> Tunnel)
    }
  }
  return candidates[0];
}

export async function loginWithPin(baseUrl: string, pin: string): Promise<ApiAuthResponse> {
  const target = normalizeBaseUrl(baseUrl);
  const res = await fetchWithTimeout(
    `${target}/api/mobile/auth`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    },
    6000
  );
  const data = (await res.json()) as ApiAuthResponse;
  if (!res.ok || !data.ok || !data.token) {
    throw new Error(data.message || `Erreur connexion (${res.status})`);
  }
  return data;
}

export async function exchangePairingCode(payload: PairingPayload): Promise<ApiAuthResponse & { usedBaseUrl: string }> {
  const baseUrl = await resolveReachableUrl(payload.lanUrl, payload.publicUrl);
  const res = await fetchWithTimeout(
    `${baseUrl}/api/mobile/pair/echanger`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: payload.code }),
    },
    6000
  );
  const data = (await res.json()) as ApiAuthResponse;
  if (!res.ok || !data.ok || !data.token) {
    throw new Error(data.message || `Échec appairage (${res.status})`);
  }
  return { ...data, usedBaseUrl: baseUrl };
}

export async function fetchTelemetry(session: SessionConfig): Promise<TelemetrySnapshot> {
  const res = await fetchWithTimeout(
    `${session.activeUrl}/api/mobile/telemetry`,
    {
      method: "GET",
      headers: { "x-keranos-token": session.token },
    },
    5000
  );
  const data = (await res.json()) as TelemetrySnapshot & { message?: string };
  if (!res.ok || !data.ok) {
    throw new Error(data.message || `Erreur télémétrie (${res.status})`);
  }
  return data;
}

export async function runTerminalCommand(
  session: SessionConfig,
  commande: string,
  confirme = false
): Promise<{ sortie: string; ok: boolean }> {
  const res = await fetchWithTimeout(
    `${session.activeUrl}/api/mobile/terminal`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-keranos-token": session.token,
      },
      body: JSON.stringify({ commande, confirme, timeout: 60 }),
    },
    65000
  );
  const data = (await res.json()) as { ok: boolean; sortie?: string; message?: string };
  if (!res.ok) {
    throw new Error(data.message || `Erreur terminal (${res.status})`);
  }
  return { ok: Boolean(data.ok), sortie: String(data.sortie || data.message || "") };
}

export async function triggerQuickAction(session: SessionConfig, actionNom: string): Promise<string> {
  const res = await fetchWithTimeout(
    `${session.activeUrl}/api/mobile/action`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-keranos-token": session.token,
      },
      body: JSON.stringify({ action: actionNom }),
    },
    8000
  );
  const data = (await res.json()) as { ok?: boolean; message?: string; resultat?: string };
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `Action impossible (${res.status})`);
  }
  return String(data.message || data.resultat || "Action exécutée.");
}

export async function toggleTunnel(session: SessionConfig, start: boolean): Promise<string> {
  const endpoint = start ? "/api/mobile/tunnel/demarrer" : "/api/mobile/tunnel/arreter";
  const res = await fetchWithTimeout(
    `${session.activeUrl}${endpoint}`,
    {
      method: "POST",
      headers: { "x-keranos-token": session.token },
    },
    15000
  );
  const data = (await res.json()) as { ok?: boolean; message?: string; url?: string };
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `Erreur tunnel (${res.status})`);
  }
  return String(data.url || data.message || "OK");
}

export async function logoutSession(session: SessionConfig): Promise<void> {
  try {
    await fetchWithTimeout(
      `${session.activeUrl}/api/mobile/logout`,
      {
        method: "POST",
        headers: { "x-keranos-token": session.token },
      },
      3000
    );
  } catch {
    // Ignore erreur reseau lors de la deconnexion locale
  }
}

export function buildWsUrl(baseUrl: string): string {
  const clean = normalizeBaseUrl(baseUrl);
  return `${clean.replace(/^http/i, "ws")}/ws/riot`;
}
