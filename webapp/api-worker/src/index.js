const BACKEND_URL = "https://3.107.191.151.sslip.io";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type,X-Telegram-Init-Data",
        }
      });
    }

    const targetUrl = BACKEND_URL + url.pathname + url.search;

    // Create a new Request object to forward cleanly without modifying restricted headers
    const reqHeaders = new Headers(request.headers);
    reqHeaders.delete("host");

    const fetchInit = {
      method: request.method,
      headers: reqHeaders,
      redirect: "manual"
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      fetchInit.body = request.body;
    }

    try {
      const response = await fetch(targetUrl, fetchInit);
      const resHeaders = new Headers(response.headers);
      resHeaders.set("Access-Control-Allow-Origin", "*");
      resHeaders.set("Access-Control-Allow-Headers", "Content-Type,X-Telegram-Init-Data");
      resHeaders.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: resHeaders
      });
    } catch (err) {
      return new Response(JSON.stringify({ ok: false, error: String(err) }), {
        status: 502,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }
  }
};
