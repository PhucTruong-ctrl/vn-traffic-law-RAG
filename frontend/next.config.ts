import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
  },
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendInternalUrl}/api/v1/:path*` },
      { source: "/documents/:path*", destination: `${backendInternalUrl}/api/v1/documents/:path*` },
    ];
  },
};

export default nextConfig;
