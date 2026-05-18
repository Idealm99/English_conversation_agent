import { API_BASE_URL } from '@/config';
import type { ChatRequest, ChatResponse, DeviceRegisterRequest } from '@/types';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<TBody, TResult>(
  path: string,
  method: 'GET' | 'POST' | 'DELETE',
  body?: TBody,
): Promise<TResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new ApiError(response.status, text || response.statusText);
  }
  if (response.status === 204) {
    return undefined as TResult;
  }
  return (await response.json()) as TResult;
}

export const api = {
  // 영어 회화 채팅 — 백엔드 /conversation (FAQ RAG 미사용, 순수 Gemini chat).
  chat(payload: ChatRequest): Promise<ChatResponse> {
    return request<ChatRequest, ChatResponse>('/conversation', 'POST', payload);
  },
  resetSession(sessionId: string): Promise<void> {
    return request<undefined, void>(`/conversation/${encodeURIComponent(sessionId)}`, 'DELETE');
  },
  registerDevice(payload: DeviceRegisterRequest) {
    return request('/devices/register', 'POST', payload);
  },
};

export { ApiError };
