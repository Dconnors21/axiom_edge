import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";

const nextConfig: NextConfig = {};

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
