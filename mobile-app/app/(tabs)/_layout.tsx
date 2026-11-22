import { Redirect, Tabs } from "expo-router";
import { Activity, Bot, Settings, Terminal } from "lucide-react-native";
import { useRiot } from "../../src/context/RiotContext";

export default function TabsLayout() {
  const { session, booting } = useRiot();

  if (!booting && !session) {
    return <Redirect href="/pair" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: "#0F1115" },
        headerTintColor: "#F3F4F6",
        headerTitleStyle: { fontWeight: "700", fontSize: 15 },
        tabBarStyle: {
          backgroundColor: "#0F1115",
          borderTopColor: "#222631",
          height: 60,
          paddingBottom: 6,
        },
        tabBarActiveTintColor: "#D97757",
        tabBarInactiveTintColor: "#6B7280",
      }}
    >
      <Tabs.Screen
        name="chat"
        options={{
          title: "Agent",
          tabBarIcon: ({ color, size }) => <Bot size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="cockpit"
        options={{
          title: "Cockpit",
          tabBarIcon: ({ color, size }) => <Activity size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="terminal"
        options={{
          title: "Terminal",
          tabBarIcon: ({ color, size }) => <Terminal size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Réglages",
          tabBarIcon: ({ color, size }) => <Settings size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
