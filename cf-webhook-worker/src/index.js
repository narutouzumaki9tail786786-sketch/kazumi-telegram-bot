// Kazumi Telegram Webhook Proxy Worker (Exact pattern as 'store' worker)
const BACKEND_URL = "http://3.107.191.151";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Forward request to VPS Flask backend on port 5010
    const targetUrl = BACKEND_URL + url.pathname + url.search;

    const newHeaders = new Headers();
    for (const [key, value] of request.headers.entries()) {
      const lowKey = key.toLowerCase();
      if (!["host", "cf-ray", "cf-visitor", "cf-connecting-ip", "cf-ipcountry", "content-length", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip"].includes(lowKey)) {
        newHeaders.set(key, value);
      }
    }

    const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for") || "";
    newHeaders.set("X-Forwarded-Host", url.hostname);
    newHeaders.set("X-Forwarded-Proto", "https");
    if (clientIp) {
      newHeaders.set("X-Forwarded-For", clientIp);
      newHeaders.set("X-Real-IP", clientIp);
    }

    const fetchInit = {
      method: request.method,
      headers: newHeaders,
      redirect: "manual"
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      fetchInit.body = request.body;
    }

    try {
      const response = await fetch(targetUrl, fetchInit);
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: new Headers(response.headers)
      });
    } catch (err) {
      console.error("Webhook proxy error:", err);
      // Return 200 OK to Telegram so Telegram doesn't retry flood
      return new Response(JSON.stringify({ ok: true, proxied: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
