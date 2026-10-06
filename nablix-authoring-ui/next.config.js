/** @type {import('next').NextConfig} */

// The authoring API (Saravanan's student-model service, :8080) sends no CORS
// headers, so the browser cannot call it from another origin. The portal's own
// server forwards /authoring and /auth/login to it instead — the same thing
// nginx does for nablix.ai/nablix-auth/.
const AUTHORING_TARGET = process.env.AUTHORING_PROXY_TARGET ?? 'https://nablix.ai/nablix-auth';

// PORTAL_EXPORT=1 builds the static site for the VM (nablix.ai/app/portal/ —
// under nginx's existing /app/ location, since adding one needs sudo there),
// where the API is reached through nginx's existing /nablix-auth/ proxy instead.
const exporting = process.env.PORTAL_EXPORT === '1';

const nextConfig = exporting ? {
  reactStrictMode: true,
  output: 'export',
  basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? '/portal',
  trailingSlash: true,
  images: { unoptimized: true },
} : {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: '/authoring/:path*', destination: `${AUTHORING_TARGET}/authoring/:path*` },
      { source: '/auth/login', destination: `${AUTHORING_TARGET}/auth/login` },
    ];
  },
};

module.exports = nextConfig;
