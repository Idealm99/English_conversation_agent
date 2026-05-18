import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';

import { api } from '@/api/client';

// Expo Go (SDK 53+) 에서는 Android remote push 가 빠졌다.
// 푸시는 dev build / production build 에서만 제대로 동작하므로 Expo Go 면 등록을 건너뛴다.
const IS_EXPO_GO = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

interface State {
  token: string | null;
  error: string | null;
  loading: boolean;
}

// 포그라운드에서도 배너/사운드를 노출한다. Expo Go 에선 어차피 무시되므로 생략.
if (!IS_EXPO_GO) {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}


async function fetchExpoPushToken(): Promise<string> {
  if (!Device.isDevice) {
    throw new Error('실제 디바이스에서만 푸시 토큰을 받을 수 있습니다 (시뮬레이터 X).');
  }

  // 권한 요청 (Android 13+, iOS 모두).
  const existing = await Notifications.getPermissionsAsync();
  let granted = existing.status === 'granted';
  if (!granted) {
    const requested = await Notifications.requestPermissionsAsync();
    granted = requested.status === 'granted';
  }
  if (!granted) {
    throw new Error('알림 권한이 거부되었습니다.');
  }

  if (Platform.OS === 'android') {
    // Android는 채널 설정이 필수.
    await Notifications.setNotificationChannelAsync('default', {
      name: 'default',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FFFFFF',
    });
  }

  const tokenResponse = await Notifications.getExpoPushTokenAsync();
  return tokenResponse.data;
}


export function usePushRegistration(sessionId: string | null): State {
  const [state, setState] = useState<State>({ token: null, error: null, loading: false });
  const registered = useRef(false);

  useEffect(() => {
    if (!sessionId || registered.current) return;
    registered.current = true;

    // Expo Go 에서는 푸시 자체가 지원되지 않으므로 조용히 건너뛴다.
    if (IS_EXPO_GO) {
      setState({ token: null, error: 'expo-go (push 미지원)', loading: false });
      return;
    }

    setState((s) => ({ ...s, loading: true }));

    (async () => {
      try {
        const token = await fetchExpoPushToken();
        await api.registerDevice({
          session_id: sessionId,
          push_token: token,
          platform: 'expo',
        });
        setState({ token, error: null, loading: false });
      } catch (e) {
        // 권한 거부/시뮬레이터 등은 치명적이지 않으므로 콘솔만 남기고 진행.
        const message = e instanceof Error ? e.message : String(e);
        console.warn('[push] 등록 실패:', message);
        setState({ token: null, error: message, loading: false });
        registered.current = false; // 다음 mount에서 재시도 허용.
      }
    })();
  }, [sessionId]);

  return state;
}
