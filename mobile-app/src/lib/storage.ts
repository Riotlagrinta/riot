import * as SecureStore from "expo-secure-store";
import type { SessionConfig } from "../types/riot";

const KEY_SESSION = "riot_mobile_session_v1";

export async function loadSession(): Promise<SessionConfig | null> {
  try {
    const raw = await SecureStore.getItemAsync(KEY_SESSION);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SessionConfig>;
    if (!parsed.token || (!parsed.lanUrl && !parsed.publicUrl && !parsed.activeUrl)) {
      return null;
    }
    return {
      token: String(parsed.token),
      lanUrl: String(parsed.lanUrl || ""),
      publicUrl: String(parsed.publicUrl || ""),
      activeUrl: String(parsed.activeUrl || parsed.lanUrl || parsed.publicUrl || ""),
      requireBiometric: parsed.requireBiometric !== false,
    };
  } catch {
    return null;
  }
}

export async function saveSession(cfg: SessionConfig): Promise<void> {
  await SecureStore.setItemAsync(KEY_SESSION, JSON.stringify(cfg));
}

export async function clearSession(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEY_SESSION);
  } catch {
    // Ignore si deja supprime
  }
}
