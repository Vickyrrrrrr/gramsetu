/** @type {import('next').NextConfig} */

// When deployed to Vercel, set NEXT_PUBLIC_API_URL to your Railway backend URL.
// Locally this defaults to localhost:8000.
const BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const nextConfig = {
  // serverExternalPackages is a top-level key in Next.js 14.2+
  serverExternalPackages: [],

  experimental: {
    // proxyTimeout is in milliseconds — 5 minutes for form automation
    // Note: WebSocket proxying does not work on Vercel serverless
    proxyTimeout: 5 * 60 * 1000,
  },

  async rewrites() {
    return [
      {
        // API proxy — uses BACKEND env var so Vercel can point to Railway
        source: '/api/:path*',
        destination: `${BACKEND}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
