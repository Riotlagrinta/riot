import React, { useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Send, Trash2 } from "lucide-react-native";
import { useRiot } from "../../src/context/RiotContext";
import type { ChatMessage } from "../../src/types/riot";

export default function ChatScreen() {
  const { wsConnected, streaming, messages, sendChatMessage, clearMessages } = useRiot();
  const [draft, setDraft] = useState("");
  const listRef = useRef<FlatList<ChatMessage> | null>(null);

  function submit() {
    if (!draft.trim() || !wsConnected || streaming) return;
    sendChatMessage(draft);
    setDraft("");
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={86}
    >
      <View style={styles.statusBar}>
        <View style={styles.statusLeft}>
          <View style={[styles.dot, { backgroundColor: wsConnected ? "#10B981" : "#F59E0B" }]} />
          <Text style={styles.statusText}>
            {wsConnected ? (streaming ? "Agent en cours..." : "Flux temps réel actif") : "Reconnexion WebSocket..."}
          </Text>
        </View>
        <Pressable onPress={clearMessages} style={styles.clearBtn}>
          <Trash2 size={14} color="#9CA3AF" />
          <Text style={styles.clearText}>Effacer</Text>
        </Pressable>
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.role === "user"
                ? styles.bubbleUser
                : item.role === "system"
                ? styles.bubbleSys
                : styles.bubbleAssistant,
            ]}
          >
            {item.toolSteps && item.toolSteps.length > 0 ? (
              <View style={styles.toolsBox}>
                {item.toolSteps.map((step, i) => (
                  <Text key={`${item.id}-t-${i}`} style={styles.toolText}>
                    ▸ {step}
                  </Text>
                ))}
              </View>
            ) : null}
            <Text style={styles.msgText}>{item.content}</Text>
          </View>
        )}
      />

      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={draft}
          onChangeText={setDraft}
          placeholder="Demander une action à RIOT..."
          placeholderTextColor="#6B7280"
          multiline
        />
        <Pressable
          style={[styles.sendBtn, (!wsConnected || streaming || !draft.trim()) && styles.sendDisabled]}
          onPress={submit}
          disabled={!wsConnected || streaming || !draft.trim()}
        >
          <Send size={18} color="#0B0C0E" />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#0B0C0E" },
  statusBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: "#111319",
    borderBottomWidth: 1,
    borderBottomColor: "#202531",
  },
  statusLeft: { flexDirection: "row", alignItems: "center", gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { color: "#D1D5DB", fontSize: 12 },
  clearBtn: { flexDirection: "row", alignItems: "center", gap: 5, padding: 4 },
  clearText: { color: "#9CA3AF", fontSize: 12 },
  list: { padding: 14, gap: 10 },
  bubble: { borderRadius: 12, padding: 12, maxWidth: "90%" },
  bubbleUser: { alignSelf: "flex-end", backgroundColor: "#261A16", borderWidth: 1, borderColor: "#D97757" },
  bubbleAssistant: { alignSelf: "flex-start", backgroundColor: "#14171F", borderWidth: 1, borderColor: "#242A38" },
  bubbleSys: { alignSelf: "center", backgroundColor: "#12141A", borderWidth: 1, borderColor: "#1F2430", maxWidth: "96%" },
  toolsBox: { marginBottom: 8, paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: "#242A38", gap: 2 },
  toolText: { color: "#9CA3AF", fontSize: 11, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  msgText: { color: "#F3F4F6", fontSize: 14, lineHeight: 20 },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8,
    padding: 10,
    backgroundColor: "#0F1115",
    borderTopWidth: 1,
    borderTopColor: "#222631",
  },
  input: {
    flex: 1,
    maxHeight: 110,
    backgroundColor: "#161922",
    color: "#F9FAFB",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#272C3A",
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: "#D97757",
    alignItems: "center",
    justifyContent: "center",
  },
  sendDisabled: { opacity: 0.45 },
});
