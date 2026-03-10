/** @type {import('next').NextConfig} */

// When deployed to Vercel, set NEXT_PUBLIC_BACKEND_URL to your ngrok URL.
// Locally this defaults to localhost:8000.
const BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const nextConfig = {
  // Increase the serverless function / proxy timeout to 5 minutes so
  // long-running Playwright form-fill operations don't cause ECONNRESET.
  serverExternalPackages: [],
  experimental: {
    // proxyTimeout is in milliseconds — 5 minutes for form automation
    proxyTimeout: 5 * 60 * 1000,
  },
  async rewrites() {
    return [
      {
        // WebSocket proxy — only works when Next.js runs locally (not on Vercel serverless)
        source: '/ws/:path*',
        destination: `${BACKEND}/ws/:path*`,
      },
      {
        // API proxy — uses BACKEND env var so Vercel can point to ngrok
        source: '/api/:path*',
        destination: `${BACKEND}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig

