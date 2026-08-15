// src/index.js
var BACKEND_URL = "https://menus-unknown-deviation-paul.trycloudflare.com";
var index_default = {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type,X-Telegram-Init-Data"
        }
      });
    }
    const targetUrl = BACKEND_URL + url.pathname + url.search;
    const targetHost = new URL(BACKEND_URL).hostname;
    const newHeaders = new Headers();
    for (const [key, value] of request.headers.entries()) {
      const lowKey = key.toLowerCase();
      if (!["host", "cf-ray", "cf-visitor", "cf-connecting-ip", "cf-ipcountry", "content-length", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip"].includes(lowKey)) {
        newHeaders.set(key, value);
      }
    }
    newHeaders.set("Host", targetHost);
    newHeaders.set("X-Forwarded-Host", url.hostname);
    newHeaders.set("X-Forwarded-Proto", "https");
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
export {
  index_default as default
};
//# sourceMappingURL=index.js.map
