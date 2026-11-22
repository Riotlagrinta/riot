import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export interface PushRegistrationResult {
  ok: boolean;
  token?: string;
  reason?: string;
}

export async function requestExpoPushToken(): Promise<PushRegistrationResult> {
  if (!Device.isDevice) {
    return { ok: false, reason: "Les notifications push nécessitent un smartphone physique." };
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("riot-alerts", {
      name: "Alertes RIOT",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 200, 150, 200],
      lightColor: "#D97757",
    });
  }

  const current = await Notifications.getPermissionsAsync();
  let status = current.status;
  if (status !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== "granted") {
    return { ok: false, reason: "Permission de notification refusée." };
  }

  try {
    const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
    const projectId = extra?.eas?.projectId;
    const tokenObj = projectId
      ? await Notifications.getExpoPushTokenAsync({ projectId })
      : await Notifications.getExpoPushTokenAsync();
    if (!tokenObj.data) {
      return { ok: false, reason: "Jeton push vide." };
    }
    return { ok: true, token: tokenObj.data };
  } catch (e) {
    return {
      ok: false,
      reason: e instanceof Error ? e.message : "Configuration EAS projectId requise pour le push.",
    };
  }
}
