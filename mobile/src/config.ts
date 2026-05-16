import Constants from 'expo-constants';
import { Platform } from 'react-native';

// 우선순위: app.json > 플랫폼별 기본값.
// Android 에뮬레이터에서 호스트 PC localhost는 10.0.2.2, iOS 시뮬레이터는 localhost.
const fromExtra = (Constants.expoConfig?.extra as { apiBaseUrl?: string } | undefined)?.apiBaseUrl;

const platformDefault =
  Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';

export const API_BASE_URL = fromExtra ?? platformDefault;

// 단일 사용자 PoC라 세션 ID는 디바이스에 한 번 만들어 보관한다.
// 멀티 사용자/계정이 생기면 로그인 토큰으로 교체.
export const STORAGE_KEYS = {
  sessionId: 'faq-chatbot.sessionId',
  messages: 'faq-chatbot.messages',
} as const;
