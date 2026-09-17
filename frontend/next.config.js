/** @type {import('next').NextConfig} */
// Inside Docker the backend is reachable as the `backend` service; for local
// dev set BACKEND_ORIGIN=http://127.0.0.1:8000.
const backendOrigin = process.env.BACKEND_ORIGIN || "http://backend:8000";

const nextConfig = {
  reactStrictMode: true,
  // Note: Next's built-in i18n routing is deliberately NOT used here - enabling
  // it makes the router claim /api/* and the backend proxy below stops
  // matching. Language is a stored preference instead (see lib/i18n.ts).
  async rewrites() {
    // Proxy /api/* to the backend service so the frontend can call a same-origin API.
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
  output: "standalone",
};

module.exports = nextConfig;
