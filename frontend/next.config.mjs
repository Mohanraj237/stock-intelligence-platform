/** @type {import('next').NextConfig} */
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      // afterFiles: checked after local route handlers (app/api/*), so /api/fno/* is
      // handled by the Next.js route handler and never reaches this rewrite.
      afterFiles: [
        { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      ],
    };
  },
};

export default nextConfig;
