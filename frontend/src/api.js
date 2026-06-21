const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://travel-agent-1-zm2s.onrender.com";

export async function generatePlan(payload) {
  const res = await fetch(`${API_BASE_URL}/plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;

    try {
      const body = await res.json();
      if (body?.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch (_) {}

    throw new Error(detail);
  }

  return res.json();
}