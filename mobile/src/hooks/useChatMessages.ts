import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api, ApiError } from '@/api/client';
import { STORAGE_KEYS } from '@/config';
import type { ChatMessage } from '@/types';

interface UseChatMessages {
  messages: ChatMessage[];
  sending: boolean;
  error: string | null;
  send: (text: string) => Promise<void>;
  reset: () => Promise<void>;
}

function makeId(): string {
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useChatMessages(sessionId: string | null): UseChatMessages {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hydrated = useRef(false);

  // 초기 로드.
  useEffect(() => {
    (async () => {
      const raw = await AsyncStorage.getItem(STORAGE_KEYS.messages);
      if (raw) {
        try {
          setMessages(JSON.parse(raw));
        } catch {
          await AsyncStorage.removeItem(STORAGE_KEYS.messages);
        }
      }
      hydrated.current = true;
    })();
  }, []);

  // 변경 시 디스크에 영속화.
  useEffect(() => {
    if (!hydrated.current) return;
    AsyncStorage.setItem(STORAGE_KEYS.messages, JSON.stringify(messages)).catch(() => undefined);
  }, [messages]);

  const send = useCallback(
    async (text: string) => {
      if (!sessionId) return;
      const trimmed = text.trim();
      if (!trimmed) return;

      const userMsg: ChatMessage = {
        id: makeId(),
        role: 'user',
        content: trimmed,
        createdAt: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setSending(true);
      setError(null);

      try {
        const response = await api.chat({ session_id: sessionId, message: trimmed });
        const assistantMsg: ChatMessage = {
          id: makeId(),
          role: 'assistant',
          content: response.answer,
          createdAt: Date.now(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (e) {
        const detail = e instanceof ApiError ? `[${e.status}] ${e.message}` : String(e);
        setError(detail);
      } finally {
        setSending(false);
      }
    },
    [sessionId],
  );

  const reset = useCallback(async () => {
    setMessages([]);
    await AsyncStorage.removeItem(STORAGE_KEYS.messages);
  }, []);

  return { messages, sending, error, send, reset };
}
