import type { NextConfig } from 'next';
const staticExport = process.env.STATIC_EXPORT === 'true';
const config: NextConfig = {
  output: staticExport ? 'export' : process.env.DOCKER_BUILD === 'true' ? 'standalone' : undefined,
  outputFileTracingRoot: process.cwd(),
  turbopack: {root:process.cwd()},
  ...(!staticExport ? {
    async rewrites() { return [{ source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:8000'}/:path*` }]; },
    async headers() { return [{ source: '/:path*', headers: [
      {key:'X-Content-Type-Options',value:'nosniff'}, {key:'X-Frame-Options',value:'DENY'},
      {key:'Referrer-Policy',value:'no-referrer'},
      {key:'Permissions-Policy',value:'camera=(), geolocation=(), microphone=(self)'},
    ] }]; },
  } : {}),
};
export default config;
