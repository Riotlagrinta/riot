import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Redirect } from "expo-router";
import { useRiot } from "../src/context/RiotContext";

export default function IndexRoute() {
  const { session, booting } = useRiot();

  if (booting) {
    return (
      <View style={styles.wrap}>
        <ActivityIndicator size="large" color="#D97757" />
        <Text style={styles.txt}>Connexion sécurisée à RIOT...</Text>
      </View>
    );
  }

  return <Redirect href={session ? "/(tabs)/chat" : "/pair"} />;
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: "#0B0C0E",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  txt: {
    color: "#9CA3AF",
    fontSize: 13,
  },
});
