/** @type {import('next').NextConfig} */

// When building for GitHub Pages we statically export the app and serve it from
// a repo subpath (https://<org>.github.io/<repo>/). The workflow sets
// GITHUB_PAGES=true; local dev and normal builds are unaffected.
const isPages = process.env.GITHUB_PAGES === 'true';
const repo = 'Numera-ui';

// Static export for a self-hosted deploy under a subpath (e.g. nginx on the VM
// serving the SPA at http://<host>/app/). Set EXPORT_BASE_PATH="/app" at build.
const exportBasePath = process.env.EXPORT_BASE_PATH;

const nextConfig = {
  ...(isPages
    ? {
        output: 'export',
        basePath: `/${repo}`,
        assetPrefix: `/${repo}/`,
        // Emit dir/index.html so deep links work with or without a trailing slash
        trailingSlash: true,
      }
    : exportBasePath
    ? {
        output: 'export',
        basePath: exportBasePath,
        assetPrefix: `${exportBasePath}/`,
        trailingSlash: true,
      }
    : {}),
  images: { unoptimized: true },
  // Allow KaTeX CSS to be imported from node_modules
  transpilePackages: ['react-katex'],
  webpack: (config) => {
    // Enable WebAssembly (not required now but future-proof)
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    // konva's node build references the optional native `canvas` package, which
    // isn't installed (and isn't needed in the browser). Alias it off so the
    // client bundle resolves. (react-konva 19 pulls konva's node index.)
    config.resolve = config.resolve || {};
    config.resolve.alias = { ...(config.resolve.alias || {}), canvas: false };
    return config;
  },
};

module.exports = nextConfig;
