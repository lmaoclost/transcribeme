/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone: traced, production-only server in .next/standalone (no full node_modules in runtime image)
  output: 'standalone',
  reactStrictMode: true,
  experimental: {
    scrollRestoration: true
  }
};

export default nextConfig;
