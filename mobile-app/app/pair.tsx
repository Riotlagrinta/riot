import React, { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import { QrCode, ShieldCheck, Wifi } from "lucide-react-native";
import { useRiot } from "../src/context/RiotContext";
import { parsePairingQr } from "../src/lib/api";

export default function PairScreen() {
  const router = useRouter();
  const { signInWithPin, signInWithQr } = useRiot();
  const [permission, requestPermission] = useCameraPermissions();

  const [scanning, setScanning] = useState(false);
  const [scannedLock, setScannedLock] = useState(false);
  const [serverUrl, setServerUrl] = useState("http://192.168.1.10:8790");
  const [pin, setPin] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  async function handlePinSubmit() {
    setErrorMsg("");
    if (!serverUrl.trim() || !pin.trim()) {
      setErrorMsg("Renseignez l'adresse du PC et votre code PIN.");
      return;
    }
    setLoading(true);
    try {
      await signInWithPin(serverUrl, pin);
      router.replace("/(tabs)/chat");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Connexion refusée.");
    } finally {
      setLoading(false);
    }
  }

  async function openQrScanner() {
    setErrorMsg("");
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        setErrorMsg("Permission caméra requise pour scanner le QR Code d'appairage.");
        return;
      }
    }
    setScannedLock(false);
    setScanning(true);
  }

  async function handleBarcodeScanned(rawData: string) {
    if (scannedLock || loading) return;
    const payload = parsePairingQr(rawData);
    if (!payload) {
      setErrorMsg("QR Code non reconnu (attendu : riot://pair?...).");
      return;
    }
    setScannedLock(true);
    setScanning(false);
    setLoading(true);
    try {
      await signInWithQr(payload);
      router.replace("/(tabs)/chat");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Échec de l'appairage QR.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <View style={styles.badge}>
          <ShieldCheck size={16} color="#D97757" />
          <Text style={styles.badgeText}>RIOT MOBILE NATIVE</Text>
        </View>
        <Text style={styles.title}>Connecter à votre PC</Text>
        <Text style={styles.subtitle}>
          Scannez un QR d&apos;appairage éphémère depuis RIOT Desktop ou connectez-vous via votre adresse locale / tunnel Cloudflare et PIN.
        </Text>

        {scanning ? (
          <View style={styles.cameraBox}>
            <CameraView
              style={styles.camera}
              facing="back"
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
              onBarcodeScanned={(res) => {
                void handleBarcodeScanned(res.data);
              }}
            />
            <Pressable style={styles.cancelScan} onPress={() => setScanning(false)}>
              <Text style={styles.cancelScanText}>Fermer la caméra</Text>
            </Pressable>
          </View>
        ) : (
          <Pressable style={styles.qrBtn} onPress={() => void openQrScanner()} disabled={loading}>
            <QrCode size={19} color="#0B0C0E" />
            <Text style={styles.qrBtnText}>Scanner le QR Code d&apos;appairage</Text>
          </Pressable>
        )}

        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Wifi size={16} color="#10B981" />
            <Text style={styles.cardTitle}>Connexion manuelle (LAN ou Tunnel)</Text>
          </View>

          <Text style={styles.label}>URL RIOT (Wi-Fi local ou https://...trycloudflare.com)</Text>
          <TextInput
            style={styles.input}
            value={serverUrl}
            onChangeText={setServerUrl}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="http://192.168.1.25:8790"
            placeholderTextColor="#6B7280"
          />

          <Text style={styles.label}>Code PIN RIOT</Text>
          <TextInput
            style={styles.input}
            value={pin}
            onChangeText={setPin}
            secureTextEntry
            keyboardType="number-pad"
            placeholder="Votre code PIN"
            placeholderTextColor="#6B7280"
          />

          {errorMsg ? <Text style={styles.err}>{errorMsg}</Text> : null}

          <Pressable style={styles.submitBtn} onPress={() => void handlePinSubmit()} disabled={loading}>
            {loading ? (
              <ActivityIndicator size="small" color="#0B0C0E" />
            ) : (
              <Text style={styles.submitText}>Se connecter</Text>
            )}
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#0B0C0E" },
  container: { flexGrow: 1, justifyContent: "center", padding: 22, gap: 16 },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: "#161922",
    borderWidth: 1,
    borderColor: "#262B38",
  },
  badgeText: { color: "#D97757", fontSize: 11, fontWeight: "700", letterSpacing: 0.7 },
  title: { color: "#F9FAFB", fontSize: 26, fontWeight: "700" },
  subtitle: { color: "#9CA3AF", fontSize: 13.5, lineHeight: 20 },
  qrBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    backgroundColor: "#D97757",
    paddingVertical: 14,
    borderRadius: 12,
  },
  qrBtnText: { color: "#0B0C0E", fontWeight: "700", fontSize: 14.5 },
  cameraBox: {
    height: 280,
    borderRadius: 14,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#D97757",
    position: "relative",
  },
  camera: { flex: 1 },
  cancelScan: {
    position: "absolute",
    bottom: 12,
    alignSelf: "center",
    backgroundColor: "rgba(11,12,14,0.86)",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#374151",
  },
  cancelScanText: { color: "#F3F4F6", fontSize: 12.5, fontWeight: "600" },
  card: {
    backgroundColor: "#14171F",
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: "#222733",
    gap: 10,
  },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 4 },
  cardTitle: { color: "#E5E7EB", fontWeight: "600", fontSize: 14 },
  label: { color: "#9CA3AF", fontSize: 12 },
  input: {
    backgroundColor: "#0B0C0E",
    borderWidth: 1,
    borderColor: "#272C3A",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
    color: "#F9FAFB",
    fontSize: 14,
  },
  err: { color: "#FCA5A5", fontSize: 12.5, marginTop: 2 },
  submitBtn: {
    backgroundColor: "#10B981",
    borderRadius: 10,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: 6,
  },
  submitText: { color: "#0B0C0E", fontWeight: "700", fontSize: 14 },
});
