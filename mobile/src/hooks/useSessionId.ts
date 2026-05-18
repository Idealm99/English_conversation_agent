import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';

import { STORAGE_KEYS } from '@/config';

function randomId(): string {
  // 충분히 충돌 가능성 낮은 간단한 ID. 필요해지면 uuid 패키지로 교체.
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useSessionId(): string | null {
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const existing = await AsyncStorage.getItem(STORAGE_KEYS.sessionId);
      if (existing) {
        if (!cancelled) setSessionId(existing);
        return;
      }
      const fresh = randomId();
      await AsyncStorage.setItem(STORAGE_KEYS.sessionId, fresh);
      if (!cancelled) setSessionId(fresh);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return sessionId;
}
