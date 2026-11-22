import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { LogOut, Bell, RefreshCw, Shield } from "lucide-react-native";
import { useRiot } from "../../src/context/RiotContext";

export default function SettingsScreen() {
  const router = useRouter();
  const {
    session,
    pushStatus,
    switchActiveRoute,
    setRequireBiometric,
    enablePushNotifications,
    testPushNotification,
    signOut,
  } = useRiot();
  const [routeMsg, setRouteMsg] = useState("");
  const [pushMsg, setPushMsg] = useState("");

  async function handleTestPush() {
    setPushMsg("Envoi en cours...");
    try {
      const msg = await testPushNotification();
      setPushMsg(msg);
    } catch (e) {
      setPushMsg(e instanceof Error ? e.message : "Erreur push");
    }
  }

  async function handleTestRoute() {
    setRouteMsg("Test des routes en cours...");
    const url = await switchActiveRoute();
    setRouteMsg(url ? `Route active : ${url}` : "Aucune route joignable.");
  }

  async function handleLogout() {
    await signOut();
    router.replace("/pair");
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Connexion serveur</Text>
        <Text style={styles.item}>Route active : {session?.activeUrl || "-"}</Text>
        <Text style={styles.item}>LAN : {session?.lanUrl || "Non configurée"}</Text>
        <Text style={styles.item}>Tunnel HTTPS : {session?.publicUrl || "Non configurée"}</Text>

        <Pressable style={styles.btn} onPress={() => void handleTestRoute()}>
          <RefreshCw size={15} color="#0B0C0E" />
          <Text style={styles.btnText}>Tester / Basculer LAN ↔ Tunnel</Text>
        </Pressable>
        {routeMsg ? <Text style={styles.info}>{routeMsg}</Text> : null}
      </View>

      <View style={styles.card}>
        <View style={styles.row}>
          <View style={styles.rowLeft}>
            <Shield size={18} color="#D97757" />
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>Protection biométrique</Text>
              <Text style={styles.sub}>Exiger empreinte / FaceID avant toute commande sensible</Text>
            </View>
          </View>
          <Switch
            value={Boolean(session?.requireBiometric)}
            onValueChange={(v) => void setRequireBiometric(v)}
            trackColor={{ false: "#374151", true: "#D97757" }}
          />
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.rowLeft}>
          <Bell size={18} color="#10B981" />
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Notifications Push Natives</Text>
            <Text style={styles.sub}>Statut : {pushStatus}</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
          <Pressable style={[styles.btn, { flex: 1, marginTop: 0 }]} onPress={() => void enablePushNotifications()}>
            <Text style={styles.btnText}>Activer</Text>
          </Pressable>
          <Pressable
            style={[styles.btn, { flex: 1, marginTop: 0, backgroundColor: "#10B981" }]}
            onPress={() => void handleTestPush()}
          >
            <Text style={styles.btnText}>Tester</Text>
          </Pressable>
        </View>
        {pushMsg ? <Text style={styles.info}>{pushMsg}</Text> : null}
      </View>

      <Pressable style={styles.logoutBtn} onPress={() => void handleLogout()}>
        <LogOut size={16} color="#FCA5A5" />
        <Text style={styles.logoutText}>Déconnecter et révoquer la session</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#0B0C0E" },
  container: { padding: 16, gap: 14 },
  card: {
    backgroundColor: "#14171F",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#222733",
    padding: 16,
    gap: 8,
  },
  title: { color: "#F3F4F6", fontWeight: "700", fontSize: 15 },
  sub: { color: "#9CA3AF", fontSize: 12.5, marginTop: 2 },
  item: { color: "#D1D5DB", fontSize: 13 },
  btn: {
    marginTop: 6,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#D97757",
    borderRadius: 10,
    paddingVertical: 11,
  },
  btnText: { color: "#0B0C0E", fontWeight: "700", fontSize: 13 },
  info: { color: "#10B981", fontSize: 12.5 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  rowLeft: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  logoutBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(239, 68, 68, 0.4)",
    backgroundColor: "rgba(239, 68, 68, 0.1)",
  },
  logoutText: { color: "#FCA5A5", fontWeight: "700", fontSize: 13.5 },
});
