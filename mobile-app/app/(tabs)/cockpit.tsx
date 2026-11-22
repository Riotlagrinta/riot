import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Camera, Cpu, Globe, Lock, VolumeX } from "lucide-react-native";
import { useRiot } from "../../src/context/RiotContext";
import { toggleTunnel, triggerQuickAction } from "../../src/lib/api";

const QUICK_ACTIONS = [
  { id: "capture_ecran", label: "Capture écran", icon: Camera },
  { id: "couper_son", label: "Couper le son", icon: VolumeX },
  { id: "verrouiller", label: "Verrouiller PC", icon: Lock },
];

export default function CockpitScreen() {
  const { session, telemetry, refreshTelemetry } = useRiot();
  const [refreshing, setRefreshing] = useState(false);
  const [actionStatus, setActionStatus] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);

  useEffect(() => {
    void refreshTelemetry().catch(() => {});
  }, [refreshTelemetry]);

  async function onRefresh() {
    setRefreshing(true);
    try {
      await refreshTelemetry();
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : "Erreur rafraîchissement.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleAction(actionId: string) {
    if (!session) return;
    setBusyAction(actionId);
    setActionStatus("");
    try {
      const msg = await triggerQuickAction(session, actionId);
      setActionStatus(msg);
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : "Erreur action.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleTunnelToggle() {
    if (!session || !telemetry) return;
    setBusyAction("tunnel");
    setActionStatus("");
    try {
      const res = await toggleTunnel(session, !telemetry.tunnel_distant);
      setActionStatus(res);
      await refreshTelemetry();
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : "Erreur tunnel.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void onRefresh()} tintColor="#D97757" />}
    >
      <View style={styles.grid}>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>CPU</Text>
          <Text style={styles.metricVal}>{telemetry ? `${telemetry.cpu_pct}%` : "--"}</Text>
        </View>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>RAM</Text>
          <Text style={styles.metricVal}>{telemetry ? `${telemetry.ram_pct}%` : "--"}</Text>
        </View>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>Disque libre</Text>
          <Text style={styles.metricVal}>{telemetry ? `${telemetry.disque_libre_go} Go` : "--"}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.rowHead}>
          <Cpu size={16} color="#D97757" />
          <Text style={styles.cardTitle}>Moteur & Réseau</Text>
        </View>
        <Text style={styles.infoLine}>Fournisseur : {telemetry?.llm_provider || "-"}</Text>
        <Text style={styles.infoLine}>Modèle actif : {telemetry?.llm_modele || "-"}</Text>
        <Text style={styles.infoLine}>IP Locale : {telemetry?.ip_locale || "-"}:{telemetry?.port || 8790}</Text>
        <Text style={styles.infoLine}>Tunnel 4G/5G : {telemetry?.url_publique || "Désactivé"}</Text>
        <Pressable
          style={[styles.tunnelBtn, telemetry?.tunnel_distant ? styles.tunnelStop : styles.tunnelStart]}
          onPress={() => void handleTunnelToggle()}
          disabled={busyAction === "tunnel"}
        >
          <Globe size={16} color="#0B0C0E" />
          <Text style={styles.tunnelBtnText}>
            {busyAction === "tunnel"
              ? "Opération en cours..."
              : telemetry?.tunnel_distant
              ? "Arrêter le tunnel distant"
              : "Démarrer le tunnel Cloudflare"}
          </Text>
        </Pressable>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Actions rapides PC</Text>
        <View style={styles.actionsWrap}>
          {QUICK_ACTIONS.map((a) => {
            const Icon = a.icon;
            const busy = busyAction === a.id;
            return (
              <Pressable key={a.id} style={styles.actionChip} onPress={() => void handleAction(a.id)} disabled={Boolean(busyAction)}>
                {busy ? <ActivityIndicator size="small" color="#D97757" /> : <Icon size={16} color="#D97757" />}
                <Text style={styles.actionText}>{a.label}</Text>
              </Pressable>
            );
          })}
        </View>
        {actionStatus ? <Text style={styles.feedback}>{actionStatus}</Text> : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#0B0C0E" },
  container: { padding: 16, gap: 14 },
  grid: { flexDirection: "row", gap: 10 },
  metricCard: {
    flex: 1,
    backgroundColor: "#14171F",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#222733",
    padding: 14,
    gap: 4,
  },
  metricLabel: { color: "#9CA3AF", fontSize: 12 },
  metricVal: { color: "#F9FAFB", fontSize: 20, fontWeight: "700" },
  card: {
    backgroundColor: "#14171F",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#222733",
    padding: 16,
    gap: 10,
  },
  rowHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  cardTitle: { color: "#F3F4F6", fontWeight: "700", fontSize: 15 },
  infoLine: { color: "#D1D5DB", fontSize: 13 },
  tunnelBtn: {
    marginTop: 4,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 12,
    borderRadius: 10,
  },
  tunnelStart: { backgroundColor: "#10B981" },
  tunnelStop: { backgroundColor: "#F59E0B" },
  tunnelBtnText: { color: "#0B0C0E", fontWeight: "700", fontSize: 13.5 },
  actionsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  actionChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: "#0B0C0E",
    borderWidth: 1,
    borderColor: "#2A3040",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
  },
  actionText: { color: "#E5E7EB", fontSize: 13, fontWeight: "500" },
  feedback: { color: "#10B981", fontSize: 12.5, marginTop: 4 },
});
