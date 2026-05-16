import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '@/types';

interface Props {
  message: ChatMessage;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  return (
    <View
      style={[
        styles.row,
        isUser ? styles.rowUser : styles.rowAssistant,
      ]}
    >
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
        <Text style={isUser ? styles.textUser : styles.textAssistant}>{message.content}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    width: '100%',
    marginVertical: 4,
    flexDirection: 'row',
  },
  rowUser: { justifyContent: 'flex-end' },
  rowAssistant: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '80%',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 16,
  },
  bubbleUser: { backgroundColor: '#2563eb' },
  bubbleAssistant: { backgroundColor: '#e5e7eb' },
  textUser: { color: '#ffffff', fontSize: 16 },
  textAssistant: { color: '#111827', fontSize: 16 },
});
