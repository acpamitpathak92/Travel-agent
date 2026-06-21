// Single call into the backend planner. The Vite dev server proxies /plan
// to the FastAPI app on :8000 (see vite.config.js).
export async function generatePlan(payload) {
  const res = await fetch("/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = JSON.stringify(body.detail);
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}
