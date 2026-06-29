/** @type {import('next').NextConfig} */

// When building for GitHub Pages we statically export the app and serve it from
// a repo subpath (https://<org>.github.io/<repo>/). The workflow sets
// GITHUB_PAGES=true; local dev and normal builds are unaffected.
const isPages = process.env.GITHUB_PAGES === 'true';
const repo = 'Numera-ui';

const nextConfig = {
  ...(isPages
    ? {
        output: 'export',
        basePath: `/${repo}`,
        assetPrefix: `/${repo}/`,
        // Emit dir/index.html so deep links work with or without a trailing slash
        trailingSlash: true,
      }
    : {}),
  images: { unoptimized: true },
  // Allow KaTeX CSS to be imported from node_modules
  transpilePackages: ['react-katex'],
  webpack: (config) => {
    // Enable WebAssembly (not required now but future-proof)
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    return config;
  },
};

module.exports = nextConfig;
