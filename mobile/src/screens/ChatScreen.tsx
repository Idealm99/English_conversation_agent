import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { MessageBubble } from '@/components/MessageBubble';
import { useChatMessages } from '@/hooks/useChatMessages';
import { usePushRegistration } from '@/hooks/usePushRegistration';
import { useSessionId } from '@/hooks/useSessionId';
import type { ChatMessage } from '@/types';

export function ChatScreen() {
  const sessionId = useSessionId();
  const { messages, sending, error, send, reset } = useChatMessages(sessionId);
  const push = usePushRegistration(sessionId);
  const [draft, setDraft] = useState('');
  const listRef = useRef<FlatList<ChatMessage>>(null);

  const handleSend = useCallback(async () => {
    const text = draft;
    setDraft('');
    await send(text);
    // 다음 프레임에 스크롤 (메시지 push 후 layout 완료 대기).
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
  }, [draft, send]);

  if (!sessionId) {
    return (
      <SafeAreaView style={styles.loading}>
        <ActivityIndicator />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>FAQ Chatbot</Text>
          <Text style={styles.subtitle}>
            세션 {sessionId.slice(0, 12)}…
            {push.token ? '  ·  푸시 ✓' : push.error ? '  ·  푸시 ✗' : '  ·  푸시 …'}
          </Text>
        </View>
        <Pressable onPress={reset} hitSlop={8}>
          <Text style={styles.resetButton}>초기화</Text>
        </Pressable>
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
      />

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
      >
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="질문을 입력하세요"
            placeholderTextColor="#9ca3af"
            editable={!sending}
            multiline
          />
          <Pressable
            style={[styles.sendButton, (sending || !draft.trim()) && styles.sendButtonDisabled]}
            disabled={sending || !draft.trim()}
            onPress={handleSend}
          >
            {sending ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendText}>전송</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#ffffff' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e5e7eb',
  },
  title: { fontSize: 18, fontWeight: '600', color: '#111827' },
  subtitle: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  resetButton: { color: '#2563eb', fontSize: 14, fontWeight: '500' },
  list: { padding: 12, paddingBottom: 16 },
  errorBanner: {
    backgroundColor: '#fee2e2',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  errorText: { color: '#991b1b', fontSize: 13 },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#e5e7eb',
    backgroundColor: '#ffffff',
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#f3f4f6',
    borderRadius: 20,
    fontSize: 16,
    color: '#111827',
  },
  sendButton: {
    backgroundColor: '#2563eb',
    paddingHorizontal: 16,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: { backgroundColor: '#9ca3af' },
  sendText: { color: '#ffffff', fontWeight: '600' },
});
