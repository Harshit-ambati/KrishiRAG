import { cp, mkdir } from 'node:fs/promises';

const source = new URL('../frontend/', import.meta.url);
const output = new URL('../.vercel-farmer/', import.meta.url);

await mkdir(output, { recursive: true });
await Promise.all([
  cp(new URL('index.html', source), new URL('index.html', output)),
  cp(new URL('css/styles.css', source), new URL('static/css/styles.css', output)),
  cp(new URL('js/app.js', source), new URL('static/js/app.js', output)),
  cp(new URL('js/translations.js', source), new URL('static/js/translations.js', output)),
  cp(new URL('assets/', source), new URL('static/assets/', output), { recursive: true }),
  cp(new URL('fonts/', source), new URL('static/fonts/', output), { recursive: true }),
]);
