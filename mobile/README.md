# FAQ Chatbot Mobile (Expo + React Native)

PoC: 텍스트 채팅 + Expo 푸시 토큰 등록.

## 사전 준비

```bash
cd mobile
npm install            # 또는 yarn / pnpm
```

백엔드(FastAPI)를 `0.0.0.0:8000` 으로 띄워둔다.

## 실행

```bash
# iOS 시뮬레이터 (macOS)
npm run ios

# Android 에뮬레이터
npm run android

# Expo Go 앱으로 실제 디바이스에서 (같은 Wi-Fi 필요)
npm start
```

## 백엔드 주소 바꾸기

`app.json` 의 `expo.extra.apiBaseUrl` 을 수정하거나, 그대로 두면 플랫폼 기본값을 사용합니다:

- Android 에뮬레이터: `http://10.0.2.2:8000` (호스트 PC localhost)
- iOS 시뮬레이터: `http://localhost:8000`
- 실제 디바이스: 같은 네트워크에서 PC 내부 IP(`http://192.168.x.x:8000`) 등으로 직접 지정해야 합니다.

## 푸시 알림 테스트

1. 앱을 **실제 디바이스**에서 실행 (시뮬레이터는 Expo Push 미지원).
2. 앱 헤더에 "푸시 ✓" 가 뜨면 토큰이 백엔드에 등록된 상태.
3. 백엔드에 발송 요청:

```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "content-type: application/json" \
  -d '{"session_id":"<앱 헤더의 세션 ID>","title":"테스트","body":"안녕하세요!"}'
```

## 다음 단계 (음성)

- WebSocket 엔드포인트(`/voice/stream`) 추가 후, `expo-av` 로 마이크 캡처
- 백엔드에서 GCP Speech-to-Text(streaming) ↔ Gemini ↔ GCP Text-to-Speech 연결
- Expo bare workflow 또는 `expo prebuild` 로 네이티브 모듈(필요 시) 추가
