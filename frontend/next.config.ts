import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

    return [{ source: "/api/v1/:path*", destination: `${backendInternalUrl}/api/v1/:path*` }];
  },
};

export default nextConfig;
