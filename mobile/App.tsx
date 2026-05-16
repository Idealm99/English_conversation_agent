import { StatusBar } from 'expo-status-bar';
import React from 'react';

import { ChatScreen } from '@/screens/ChatScreen';

export default function App() {
  return (
    <>
      <StatusBar style="auto" />
      <ChatScreen />
    </>
  );
}
