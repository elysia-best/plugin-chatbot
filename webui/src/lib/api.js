/**
 * 控制台 API 客户端。
 * 所有请求都带 x-console-token，路径前缀固定为 /chat-agent/api。
 */

const API_BASE = '/chat-agent/api';

export const TOKEN_STORAGE_KEY = 'chatbot-console-token';

function errorFromResponse(response, payload) {
  const detail = payload?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    return first?.msg || `请求失败（${response.status}）`;
  }
  return `请求失败（${response.status}）`;
}

export async function api(token, path, method = 'GET', body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'content-type': 'application/json', 'x-console-token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorFromResponse(response, payload));
  return payload;
}

export async function apiBlob(token, path) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'x-console-token': token },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(errorFromResponse(response, payload));
  }
  return response.blob();
}

export function readStoredToken() {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function storeToken(token) {
  try {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    /* 隐私模式下 sessionStorage 可能不可用，忽略即可 */
  }
}

export function clearStoredToken() {
  try {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* 同上 */
  }
}
