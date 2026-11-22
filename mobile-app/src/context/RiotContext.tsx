import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Haptics from "expo-haptics";
import {
  buildWsUrl,
  exchangePairingCode,
  fetchTelemetry,
  loginWithPin,
  logoutSession,
  normalizeBaseUrl,
  registerPushToken,
  resolveReachableUrl,
  sendTestPush,
  unregisterPushToken,
} from "../lib/api";
import { requestExpoPushToken } from "../lib/notifications";
import { clearSession, loadSession, saveSession } from "../lib/storage";
import type { ChatMessage, PairingPayload, SessionConfig, TelemetrySnapshot, WsServerEvent } from "../types/riot";

interface RiotContextValue {
  session: SessionConfig | null;
  booting: boolean;
  wsConnected: boolean;
  streaming: boolean;
  telemetry: TelemetrySnapshot | null;
  messages: ChatMessage[];
  pushToken: string | null;
  pushStatus: string;
  signInWithPin: (serverUrl: string, pin: string) => Promise<void>;
  signInWithQr: (payload: PairingPayload) => Promise<void>;
  signOut: () => Promise<void>;
  refreshTelemetry: () => Promise<void>;
  sendChatMessage: (text: string) => void;
  clearMessages: () => void;
  setRequireBiometric: (enabled: boolean) => Promise<void>;
  switchActiveRoute: () => Promise<string>;
  enablePushNotifications: () => Promise<void>;
  testPushNotification: () => Promise<string>;
}

const RiotContext = createContext<RiotContextValue | null>(null);

export function RiotProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionConfig | null>(null);
  const [booting, setBooting] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [telemetry, setTelemetry] = useState<TelemetrySnapshot | null>(null);
  const [pushToken, setPushToken] = useState<string | null>(null);
  const [pushStatus, setPushStatus] = useState("Non configurées");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "system",
      content: "Connecté à RIOT Mobile. Envoyez une consigne, inspectez votre PC ou lancez une commande terminal.",
      timestamp: Date.now(),
    },
  ]);

  const wsRef = useRef<WebSocket | null>(null);
  const activeAssistantId = useRef<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const saved = await loadSession();
      if (saved && mounted) {
        try {
          const activeUrl = await resolveReachableUrl(saved.lanUrl, saved.publicUrl, saved.token);
          const updated = { ...saved, activeUrl };
          setSession(updated);
          await saveSession(updated);
        } catch {
          setSession(saved);
        }
      }
      if (mounted) setBooting(false);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!session) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      return;
    }

    let closed = false;
    const ws = new WebSocket(buildWsUrl(session.activeUrl));
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token: session.token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data || "{}")) as WsServerEvent;
        if (data.type === "auth_ok") {
          setWsConnected(true);
        } else if (data.type === "telemetry") {
          setTelemetry((prev) => ({
            ...(prev || { ok: true, cpu_pct: 0, ram_pct: 0, disque_libre_go: 0 }),
            ok: true,
            cpu_pct: data.cpu_pct ?? prev?.cpu_pct ?? 0,
            ram_pct: data.ram_pct ?? prev?.ram_pct ?? 0,
            disque_libre_go: data.disque_libre_go ?? prev?.disque_libre_go ?? 0,
          }));
        } else if (data.type === "tool" && data.nom) {
          const stepLabel = `${data.nom}${data.extrait ? ` -> ${data.extrait.slice(0, 80)}` : ""}`;
          setMessages((prev) => {
            const targetId = activeAssistantId.current;
            if (!targetId) return prev;
            return prev.map((m) =>
              m.id === targetId ? { ...m, toolSteps: [...(m.toolSteps || []), stepLabel] } : m
            );
          });
        } else if (data.type === "token" || data.type === "text" || data.type === "done" || data.type === "reponse") {
          const textChunk = String(data.texte || data.message || "");
          if (textChunk) {
            setMessages((prev) => {
              const targetId = activeAssistantId.current;
              if (!targetId) {
                return [...prev, { id: String(Date.now()), role: "assistant", content: textChunk, timestamp: Date.now() }];
              }
              return prev.map((m) =>
                m.id === targetId
                  ? { ...m, content: data.type === "token" ? m.content + textChunk : textChunk }
                  : m
              );
            });
          }
          if (data.type !== "token") {
            setStreaming(false);
            activeAssistantId.current = null;
          }
        } else if (data.type === "error") {
          const errMsg = data.erreur || data.message || "Erreur serveur RIOT.";
          setMessages((prev) => [
            ...prev,
            { id: `err-${Date.now()}`, role: "system", content: `Erreur : ${errMsg}`, timestamp: Date.now() },
          ]);
          setStreaming(false);
          activeAssistantId.current = null;
        }
      } catch {
        // Ignore trame invalide
      }
    };

    ws.onclose = () => {
      if (!closed) {
        setWsConnected(false);
        setStreaming(false);
      }
    };

    ws.onerror = () => {
      if (!closed) setWsConnected(false);
    };

    return () => {
      closed = true;
      ws.close();
    };
  }, [session]);

  const refreshTelemetry = useCallback(async () => {
    if (!session) return;
    const snap = await fetchTelemetry(session);
    setTelemetry(snap);
  }, [session]);

  const signInWithPin = useCallback(async (serverUrl: string, pin: string) => {
    const cleanUrl = normalizeBaseUrl(serverUrl);
    const rep = await loginWithPin(cleanUrl, pin);
    const nextSession: SessionConfig = {
      token: String(rep.token),
      lanUrl: cleanUrl.startsWith("http://") ? cleanUrl : "",
      publicUrl: cleanUrl.startsWith("https://") ? cleanUrl : "",
      activeUrl: cleanUrl,
      requireBiometric: true,
    };
    await saveSession(nextSession);
    setSession(nextSession);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }, []);

  const signInWithQr = useCallback(async (payload: PairingPayload) => {
    const rep = await exchangePairingCode(payload);
    const nextSession: SessionConfig = {
      token: String(rep.token),
      lanUrl: rep.lan_url || payload.lanUrl,
      publicUrl: rep.public_url || payload.publicUrl,
      activeUrl: rep.usedBaseUrl,
      requireBiometric: true,
    };
    await saveSession(nextSession);
    setSession(nextSession);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }, []);

  const enablePushNotifications = useCallback(async () => {
    if (!session) return;
    setPushStatus("Activation en cours...");
    const res = await requestExpoPushToken();
    if (!res.ok || !res.token) {
      setPushStatus(res.reason || "Push indisponible");
      return;
    }
    try {
      await registerPushToken(session, res.token, Platform.OS);
      setPushToken(res.token);
      setPushStatus("Activées ✓");
    } catch (e) {
      setPushStatus(e instanceof Error ? e.message : "Échec enregistrement push");
    }
  }, [session]);

  const testPushNotification = useCallback(async () => {
    if (!session) throw new Error("Session requise.");
    return sendTestPush(session);
  }, [session]);

  useEffect(() => {
    if (session && !pushToken) {
      void enablePushNotifications();
    }
  }, [session, pushToken, enablePushNotifications]);

  const signOut = useCallback(async () => {
    if (session) {
      if (pushToken) {
        await unregisterPushToken(session, pushToken);
      }
      await logoutSession(session);
    }
    await clearSession();
    setPushToken(null);
    setPushStatus("Non configurées");
    setSession(null);
    setTelemetry(null);
  }, [session, pushToken]);

  const sendChatMessage = useCallback(
    (text: string) => {
      const clean = text.trim();
      if (!clean || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      const now = Date.now();
      const userId = `u-${now}`;
      const assistantId = `a-${now + 1}`;
      activeAssistantId.current = assistantId;
      setStreaming(true);
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: clean, timestamp: now },
        { id: assistantId, role: "assistant", content: "Réflexion en cours...", timestamp: now + 1, toolSteps: [] },
      ]);
      wsRef.current.send(JSON.stringify({ type: "chat", message: clean }));
    },
    []
  );

  const clearMessages = useCallback(() => {
    setMessages([
      {
        id: `sys-${Date.now()}`,
        role: "system",
        content: "Historique effacé. Prêt pour une nouvelle demande.",
        timestamp: Date.now(),
      },
    ]);
  }, []);

  const setRequireBiometric = useCallback(
    async (enabled: boolean) => {
      if (!session) return;
      const updated = { ...session, requireBiometric: enabled };
      setSession(updated);
      await saveSession(updated);
    },
    [session]
  );

  const switchActiveRoute = useCallback(async () => {
    if (!session) return "";
    const activeUrl = await resolveReachableUrl(session.lanUrl, session.publicUrl, session.token);
    if (activeUrl !== session.activeUrl) {
      const updated = { ...session, activeUrl };
      setSession(updated);
      await saveSession(updated);
    }
    return activeUrl;
  }, [session]);

  return (
    <RiotContext.Provider
      value={{
        session,
        booting,
        wsConnected,
        streaming,
        telemetry,
        messages,
        pushToken,
        pushStatus,
        signInWithPin,
        signInWithQr,
        signOut,
        refreshTelemetry,
        sendChatMessage,
        clearMessages,
        setRequireBiometric,
        switchActiveRoute,
        enablePushNotifications,
        testPushNotification,
      }}
    >
      {children}
    </RiotContext.Provider>
  );
}

export function useRiot(): RiotContextValue {
  const ctx = useContext(RiotContext);
  if (!ctx) throw new Error("useRiot doit etre utilise dans RiotProvider");
  return ctx;
}
