import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { RiotProvider } from "../src/context/RiotContext";

export default function RootLayout() {
  return (
    <RiotProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: "#0B0C0E" },
        }}
      />
    </RiotProvider>
  );
}
