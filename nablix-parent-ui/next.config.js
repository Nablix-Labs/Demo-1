/** @type {import('next').NextConfig} */

// PARENT_EXPORT=1 builds the static site for the VM. It is served from
// nablix.ai/app/parent/ — under nginx's existing /app/ location, because adding
// a new location needs sudo on the box (same as the approver portal).
const exporting = process.env.PARENT_EXPORT === '1';

const basePath = exporting ? (process.env.NEXT_PUBLIC_BASE_PATH ?? '/app/parent') : '';

module.exports = {
  reactStrictMode: true,
  ...(exporting && { output: 'export', basePath, trailingSlash: true, images: { unoptimized: true } }),
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};
