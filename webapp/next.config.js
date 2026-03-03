/** @type {import('next').NextConfig} */

// When deployed to Vercel, set NEXT_PUBLIC_BACKEND_URL to your ngrok URL.
// Locally this defaults to localhost:8000.
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const nextConfig = {
  async rewrites() {
    return [
      {
        // WebSocket proxy — only works when Next.js runs locally (not on Vercel serverless)
        source: '/ws/:path*',
        destination: 'http://localhost:8000/ws/:path*',
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

