FROM node:20-alpine

WORKDIR /app

# Install git (required for npm dependencies with git:// URLs)
RUN apk add --no-cache git

# Install dependencies
COPY package.json ./
RUN npm install --production

# Copy source
COPY index.js ./

# Health check endpoint
RUN mkdir -p /app/auth_info

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD node -e "const http=require('http');http.get('http://localhost:3001/health',r=>{process.exit(r.statusCode===200?0:1)})"

EXPOSE 3001

CMD ["node", "index.js"]
