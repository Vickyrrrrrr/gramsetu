/** @type {import('next').NextConfig} */

const nextConfig = {
  experimental: {
    proxyTimeout: 5 * 60 * 1000,
  },

  async rewrites() {
    // Use environment variable for backend URL
    // Fallback to localhost:8000 for local development (mapped from Docker)
    // In Docker Compose, you should set BACKEND_URL=http://backend:8000
    const backendUrl = process.env.BACKEND_URL || 'http://backend:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig