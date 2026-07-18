import type {
  BuilderResult,
  CommunityModel,
  ForumThread,
  NewsItem
} from '../domain/types';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://qfin-terminal.onrender.com';

const configuredAgentTimeout = Number(import.meta.env.VITE_AGENT_TIMEOUT_MS || 120000);
export const AGENT_REQUEST_TIMEOUT_MS =
  Number.isFinite(configuredAgentTimeout) && configuredAgentTimeout > 0
    ? configuredAgentTimeout
    : 120000;

type AgentPayload = {
  content?: unknown;
  answer?: unknown;
  detail?: unknown;
  data?: {
    content?: unknown;
    answer?: unknown;
  };
};

export type BuilderRequest = {
  name: string;
  code: string;
  author: string;
  summary: string;
  ticker: string;
};

export type BuilderRunResponse = {
  model?: CommunityModel;
  result: BuilderResult;
};

export type BuilderModelResponse = {
  model?: CommunityModel;
};

type ForumResponse = {
  threads: ForumThread[];
  topToday: ForumThread[];
};

export interface QFinApi {
  checkHealth(): Promise<boolean>;
  requestAgentReply(cleanInput: string, attachment?: File | null): Promise<string>;
  getNews(category: string): Promise<NewsItem[]>;
  getForum(): Promise<ForumResponse>;
  createThread(input: { title: string; body: string; author: string }): Promise<void>;
  voteThread(threadId: string, direction: 'up' | 'down'): Promise<void>;
  createComment(threadId: string, input: { body: string; author: string }): Promise<void>;
  getModels(): Promise<CommunityModel[]>;
  runBuilder(input: BuilderRequest, mode: 'run' | 'private'): Promise<BuilderRunResponse>;
  publishBuilder(input: BuilderRequest): Promise<BuilderModelResponse>;
  savePrivateBuilder(input: BuilderRequest): Promise<BuilderModelResponse>;
}

export function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs?: number | null
): Promise<Response> {
  if (!timeoutMs || timeoutMs <= 0) {
    return fetch(url, options);
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, {
    ...options,
    signal: controller.signal
  }).finally(() => window.clearTimeout(timeoutId));
}

function sanitizeAssistantText(text: string): string {
  return text
    .split('\n')
    .filter((line) => line.trim() !== '---')
    .join('\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

async function readPayload(response: Response): Promise<AgentPayload> {
  return response.json().catch(() => ({} as AgentPayload));
}

function readAgentContent(payload: AgentPayload): string {
  const content =
    payload.content || payload.answer || payload.data?.content || payload.data?.answer || '';
  return sanitizeAssistantText(String(content || ''));
}

function responseError(payload: AgentPayload, fallback: string): Error {
  const detail = typeof payload.detail === 'string' ? payload.detail.trim() : '';
  return new Error(detail || fallback);
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs: number | null = 20000
): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE_URL}${path}`, options, timeoutMs);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw responseError(payload as AgentPayload, `Backend returned ${response.status}`);
  }
  return payload as T;
}

export async function requestAgentReply(
  cleanInput: string,
  attachment?: File | null
): Promise<string> {
  if (attachment) {
    const formData = new FormData();
    formData.append('message', cleanInput);
    formData.append('file', attachment);
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/agent/chat/upload`,
      { method: 'POST', body: formData },
      AGENT_REQUEST_TIMEOUT_MS
    );
    const payload = await readPayload(response);
    if (!response.ok) {
      throw responseError(payload, `Upload failed: ${response.status}`);
    }
    return readAgentContent(payload);
  }

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/agent/chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: cleanInput })
    },
    AGENT_REQUEST_TIMEOUT_MS
  );
  const payload = await readPayload(response);
  if (!response.ok) {
    throw responseError(payload, `Backend returned ${response.status}`);
  }
  return readAgentContent(payload);
}

async function readNewsPath(path: string): Promise<NewsItem[]> {
  const payload = await requestJson<{ news?: NewsItem[] }>(path, {}, 30000);
  return Array.isArray(payload.news) ? payload.news.slice(0, 5) : [];
}

async function getNews(category: string): Promise<NewsItem[]> {
  const encodedCategory = encodeURIComponent(category);
  const results = await Promise.allSettled([
    readNewsPath(`/community/news/${encodedCategory}`),
    readNewsPath(`/news/${encodedCategory}`)
  ]);
  const items = results.find(
    (result): result is PromiseFulfilledResult<NewsItem[]> =>
      result.status === 'fulfilled' && result.value.length > 0
  )?.value;
  if (!items?.length) {
    throw new Error('Backend returned no news array.');
  }
  return items;
}

const jsonHeaders = { 'Content-Type': 'application/json' };

export const qfinApi: QFinApi = {
  async checkHealth() {
    const payload = await requestJson<{ status?: string }>('/health', {}, 7000);
    return payload.status === 'ok';
  },

  requestAgentReply,
  getNews,

  async getForum() {
    const payload = await requestJson<{ threads?: ForumThread[]; top_today?: ForumThread[] }>(
      '/community/forum'
    );
    return {
      threads: Array.isArray(payload.threads) ? payload.threads : [],
      topToday: Array.isArray(payload.top_today) ? payload.top_today : []
    };
  },

  async createThread(input) {
    await requestJson('/community/forum', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(input)
    });
  },

  async voteThread(threadId, direction) {
    await requestJson(`/community/forum/${encodeURIComponent(threadId)}/vote`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ direction })
    });
  },

  async createComment(threadId, input) {
    await requestJson(`/community/forum/${encodeURIComponent(threadId)}/comments`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(input)
    });
  },

  async getModels() {
    const payload = await requestJson<{ models?: CommunityModel[] }>('/community/models');
    return Array.isArray(payload.models) ? payload.models : [];
  },

  runBuilder(input, mode) {
    const path = mode === 'private' ? '/builder/run-private' : '/builder/run';
    return requestJson<BuilderRunResponse>(path, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(input)
    }, AGENT_REQUEST_TIMEOUT_MS);
  },

  publishBuilder(input) {
    return requestJson<BuilderModelResponse>('/builder/publish', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(input)
    }, AGENT_REQUEST_TIMEOUT_MS);
  },

  savePrivateBuilder(input) {
    return requestJson<BuilderModelResponse>('/builder/save-private', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(input)
    }, AGENT_REQUEST_TIMEOUT_MS);
  }
};
