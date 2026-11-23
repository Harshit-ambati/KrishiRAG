const backend = URL.parse(process.env.RENDER_BACKEND_URL?.trim() || 'https://krishirag.onrender.com');
if (!backend || backend.protocol !== 'https:' || backend.pathname !== '/' || backend.username || backend.password ||
    backend.search || backend.hash) {
  throw new Error('Set RENDER_BACKEND_URL to the HTTPS origin of your Render service, without a path.');
}

const farmerEndpoints = [
  '/api/farm-config',
  '/api/coverage',
  '/api/forecast',
  '/api/advisories',
  '/api/advisories/:advisoryId/feedback',
];

export const config = {
  framework: null,
  installCommand: '',
  buildCommand: 'node scripts/build-farmer.mjs',
  outputDirectory: '.vercel-farmer',
  rewrites: farmerEndpoints.map(path => ({ source: path, destination: backend.origin + path })),
  headers: [
    {
      source: '/api/:path*',
      headers: [{ key: 'x-vercel-enable-rewrite-caching', value: '0' }],
    },
  ],
};
