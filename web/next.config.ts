import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";

const API_INTERNAL = process.env.API_INTERNAL ?? "http://localhost:8001";

const nextConfig: NextConfig = {
  // Proxy client-side /api/* to the FastAPI service so the browser talks to the
  // app same-origin. One HTTPS origin (tunnel or deploy) then serves everything.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL}/api/:path*` }];
  },
};

const withSerwist = withSerwistInit({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
});

// Serwist is a webpack plugin and doesn't support Turbopack. Dev runs on
// Turbopack (fast; the SW isn't needed there), so only wrap for production
// builds — which run with `next build --webpack` (see package.json).
export default process.env.NODE_ENV === "development"
  ? nextConfig
  : withSerwist(nextConfig);
