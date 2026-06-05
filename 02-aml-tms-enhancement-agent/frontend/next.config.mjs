/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',   // required for Docker multi-stage build
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
};

export default nextConfig;
