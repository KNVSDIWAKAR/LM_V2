// Thin fetch wrappers shared by every react-query hook.
// In dev, Vite proxies /api to the FastAPI server (see vite.config.js).
import { cleanDisplayMessages } from "./displayMessages";
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return cleanDisplayMessages(await res.json());
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let message = `${path} ${res.status}`;
    try {
      const data = await res.json();
      if (data && typeof data.error === "string") message = data.error;
      else if (data && typeof data.detail === "string") message = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return cleanDisplayMessages(await res.json());
}

export { API_BASE };
