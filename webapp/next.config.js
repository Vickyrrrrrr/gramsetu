/** @type {import('next').NextConfig} */

// Set NEXT_PUBLIC_API_URL on Vercel to your Railway backend URL.
// Must include https:// e.g. https://gramsetu-backend.up.railway.app
// Locally defaults to http://localhost:8000
const BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const nextConfig = {
  experimental: {
    proxyTimeout: 5 * 60 * 1000,
  },

  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
