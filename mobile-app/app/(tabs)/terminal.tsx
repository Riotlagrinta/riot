import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import { ShieldAlert, Terminal as TerminalIcon } from "lucide-react-native";
import { useRiot } from "../../src/context/RiotContext";
import { runTerminalCommand } from "../../src/lib/api";
import type { TerminalEntry } from "../../src/types/riot";

export default function TerminalScreen() {
  const { session } = useRiot();
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState(false);
  const [entries, setEntries] = useState<TerminalEntry[]>([]);

  async function execute(cmd: string, confirme: boolean) {
    if (!session) return;
    setRunning(true);
    try {
      const res = await runTerminalCommand(session, cmd, confirme);
      const needsConfirm = res.sortie.includes("CONFIRMATION_REQUISE");
      setEntries((prev) => [
        {
          id: `${Date.now()}`,
          commande: cmd,
          sortie: res.sortie || "(aucune sortie)",
          needsConfirm,
          timestamp: Date.now(),
        },
        ...prev,
      ]);
      if (needsConfirm && !confirme) {
        promptBiometricConfirmation(cmd);
      }
    } catch (e) {
      setEntries((prev) => [
        {
          id: `${Date.now()}`,
          commande: cmd,
          sortie: `[erreur] ${e instanceof Error ? e.message : "Échec commande"}`,
          needsConfirm: false,
          timestamp: Date.now(),
        },
        ...prev,
      ]);
    } finally {
      setRunning(false);
    }
  }

  function promptBiometricConfirmation(cmd: string) {
    Alert.alert(
      "Confirmation critique requise",
      `La commande suivante est marquée sensible :\n\n${cmd}\n\nConfirmer son exécution ?`,
      [
        { text: "Annuler", style: "cancel" },
        {
          text: "Autoriser",
          style: "destructive",
          onPress: () => {
            void confirmWithBiometric(cmd);
          },
        },
      ]
    );
  }

  async function confirmWithBiometric(cmd: string) {
    if (session?.requireBiometric) {
      const hasHw = await LocalAuthentication.hasHardwareAsync();
      if (hasHw) {
        const authRes = await LocalAuthentication.authenticateAsync({
          promptMessage: "Confirmer la commande terminal RIOT",
          cancelLabel: "Annuler",
        });
        if (!authRes.success) return;
      }
    }
    await execute(cmd, true);
  }

  function submit() {
    const clean = command.trim();
    if (!clean || running) return;
    setCommand("");
    void execute(clean, false);
  }

  return (
    <View style={styles.screen}>
      <View style={styles.inputBar}>
        <TerminalIcon size={16} color="#D97757" />
        <TextInput
          style={styles.input}
          value={command}
          onChangeText={setCommand}
          placeholder="git status, pytest, dir..."
          placeholderTextColor="#6B7280"
          autoCapitalize="none"
          autoCorrect={false}
          onSubmitEditing={submit}
        />
        <Pressable style={styles.runBtn} onPress={submit} disabled={running || !command.trim()}>
          {running ? <ActivityIndicator size="small" color="#0B0C0E" /> : <Text style={styles.runText}>Exécuter</Text>}
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.logs}>
        {entries.length === 0 ? (
          <Text style={styles.empty}>
            Saisissez une commande PowerShell/Shell pour l&apos;exécuter sur votre PC. Les commandes destructrices exigent une confirmation biométrique.
          </Text>
        ) : (
          entries.map((item) => (
            <View key={item.id} style={styles.entryCard}>
              <Text style={styles.cmdTitle}>$ {item.commande}</Text>
              <Text style={styles.outText}>{item.sortie}</Text>
              {item.needsConfirm ? (
                <Pressable style={styles.confirmBtn} onPress={() => void confirmWithBiometric(item.commande)}>
                  <ShieldAlert size={15} color="#0B0C0E" />
                  <Text style={styles.confirmText}>Confirmer avec biométrie</Text>
                </Pressable>
              ) : null}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#0B0C0E" },
  inputBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    backgroundColor: "#111319",
    borderBottomWidth: 1,
    borderBottomColor: "#222631",
  },
  input: {
    flex: 1,
    backgroundColor: "#0B0C0E",
    color: "#F9FAFB",
    borderWidth: 1,
    borderColor: "#272C3A",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 9,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 13,
  },
  runBtn: {
    backgroundColor: "#D97757",
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  runText: { color: "#0B0C0E", fontWeight: "700", fontSize: 13 },
  logs: { padding: 14, gap: 10 },
  empty: { color: "#6B7280", fontSize: 13, lineHeight: 20, textAlign: "center", marginTop: 28 },
  entryCard: {
    backgroundColor: "#14171F",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#222733",
    padding: 12,
    gap: 8,
  },
  cmdTitle: {
    color: "#D97757",
    fontWeight: "700",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 12.5,
  },
  outText: {
    color: "#E5E7EB",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 12,
    lineHeight: 18,
  },
  confirmBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    backgroundColor: "#F59E0B",
    paddingVertical: 9,
    borderRadius: 8,
  },
  confirmText: { color: "#0B0C0E", fontWeight: "700", fontSize: 12.5 },
});
