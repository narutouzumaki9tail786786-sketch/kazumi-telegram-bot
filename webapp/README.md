# Kazumi Mini App

React + Vite Telegram Mini App for the Kazumi bot dashboard.

## Local

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:5000"
npm install
npm run dev -- --port 5173
```

## Production Build

```powershell
$env:VITE_API_BASE_URL="https://kazumi-api-proxy.abdulstoreapi.workers.dev"
$env:VITE_BOT_USERNAME="KazumiRpgBot"
npm run build
npx wrangler pages deploy dist --project-name kazumi-mini-app
```

## Bot Environment

Set these in the bot `.env`:

```env
WEBAPP_URL=https://kazumi-mini-app.pages.dev
WEBAPP_CORS_ORIGIN=https://kazumi-mini-app.pages.dev
```

## API Proxy

The production Mini App uses a permanent Cloudflare Worker HTTPS proxy:

```text
https://kazumi-api-proxy.abdulstoreapi.workers.dev
```

The Worker forwards requests to the VPS API through the `nip.io` hostname:

```text
http://kazumi-api.13.207.203.185.nip.io:5000
```

Deploy the proxy after changes:

```powershell
cd api-worker
npx wrangler deploy
```
