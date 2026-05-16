// 백엔드 스키마와 1:1 대응. 새 필드를 추가할 때는 양쪽을 함께 갱신한다.

export type Role = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: number;
}

export interface ChatRequest {
  session_id: string;
  message: string;
  top_k?: number;
}

export interface FAQHit {
  faq_id: string;
  question: string;
  answer: string;
  score: number;
  distance?: number | null;
  metadata?: Record<string, unknown>;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sources: FAQHit[];
  used_cache: boolean;
  created_at: string;
}

export interface DeviceRegisterRequest {
  session_id: string;
  push_token: string;
  platform: 'expo' | 'fcm' | 'apns';
  locale?: string | null;
}
