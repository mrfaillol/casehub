import { createHash } from 'node:crypto';
import { dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import { minify as terserMinify } from 'terser';

const repoRoot = path.resolve(dirname(fileURLToPath(import.meta.url)), '..');

const assets = [
  {
    source: 'static/css/widgets.css',
    target: 'static/css/widgets.min.css',
    type: 'css',
  },
  {
    source: 'static/css/templates/dashboard_modular.css',
    target: 'static/css/templates/dashboard_modular.min.css',
    type: 'css',
  },
  {
    source: 'static/css/templates/dashboard.css',
    target: 'static/css/templates/dashboard.min.css',
    type: 'css',
  },
  {
    source: 'static/js/dashboard-widgets.js',
    target: 'static/js/dashboard-widgets.min.js',
    type: 'js',
  },
  {
    source: 'static/js/tab-manager.js',
    target: 'static/js/tab-manager.min.js',
    type: 'js',
  },
  {
    source: 'static/js/ticket-modal.js',
    target: 'static/js/ticket-modal.min.js',
    type: 'js',
  },
  // High-impact assets for Basic/neuromorphic mode
  {
    source: 'static/css/casehub-browser-basic.css',
    target: 'static/css/casehub-browser-basic.min.css',
    type: 'css',
  },
  {
    source: 'static/css/casehub-login-basic.css',
    target: 'static/css/casehub-login-basic.min.css',
    type: 'css',
  },
  {
    source: 'static/css/casehub-theme.css',
    target: 'static/css/casehub-theme.min.css',
    type: 'css',
  },
  {
    source: 'static/css/casehub-release-notice.css',
    target: 'static/css/casehub-release-notice.min.css',
    type: 'css',
  },
  {
    source: 'static/css/tab-bar.css',
    target: 'static/css/tab-bar.min.css',
    type: 'css',
  },
  {
    source: 'static/js/casehub-login-organic.js',
    target: 'static/js/casehub-login-organic.min.js',
    type: 'js',
  },
  {
    source: 'static/js/casehub-browser-basic.js',
    target: 'static/js/casehub-browser-basic.min.js',
    type: 'js',
  },
  // High-impact shared CSS (used in all themes)
  {
    source: 'static/css/design-system.css',
    target: 'static/css/design-system.min.css',
    type: 'css',
  },
  {
    source: 'static/css/liquid-glass.css',
    target: 'static/css/liquid-glass.min.css',
    type: 'css',
  },
  {
    source: 'static/brand-kit/tokens.css',
    target: 'static/brand-kit/tokens.min.css',
    type: 'css',
  },
];

function sha256(text) {
  return createHash('sha256').update(text).digest('hex').slice(0, 12);
}

function brandKitFallbackFaviconUrl() {
  const manifestPath = path.join(repoRoot, 'static/brand-kit/manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const fallback = manifest.fallback_favicon || 'favicon/casehub-favicon-degrade-4.svg';
  if (fallback.startsWith('/') || fallback.includes('..')) {
    throw new Error(`Invalid brand-kit fallback_favicon: ${fallback}`);
  }
  return `/static/brand-kit/${fallback}`;
}

function assertBrandKitFallback(source, assetSource) {
  if (assetSource !== 'static/brand-kit/tokens.css') return;
  const expected = `--casehub-favicon: url("${brandKitFallbackFaviconUrl()}")`;
  if (!source.includes(expected)) {
    throw new Error(`static/brand-kit/tokens.css must keep --casehub-favicon in sync with manifest.json fallback_favicon (${expected}).`);
  }
}

function preserveCalcPlusSpacing(css) {
  let output = '';
  let index = 0;

  while (index < css.length) {
    if (css.startsWith('calc(', index)) {
      const bodyStart = index + 5;
      let depth = 1;
      let cursor = bodyStart;

      while (cursor < css.length && depth > 0) {
        const char = css[cursor];
        if (char === '(') depth += 1;
        if (char === ')') depth -= 1;
        cursor += 1;
      }

      const bodyEnd = depth === 0 ? cursor - 1 : css.length;
      const body = css.slice(bodyStart, bodyEnd).replace(/\s*\+\s*/g, ' + ');
      output += `calc(${body}${depth === 0 ? ')' : ''}`;
      index = cursor;
    } else {
      output += css[index];
      index += 1;
    }
  }

  return output;
}

function minifyCss(source) {
  const minified = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\s+/g, ' ')
    .replace(/\s*([{}:;,>+~])\s*/g, '$1')
    .replace(/;}/g, '}')
    .trim();

  return preserveCalcPlusSpacing(minified);
}

async function minify(source, type) {
  if (type === 'css') return minifyCss(source);
  if (type === 'js') {
    let result;
    try {
      result = await terserMinify(source, {
        compress: { drop_console: false },
        mangle: true,
        module: /\bimport\s/.test(source),
      });
    } catch (err) {
      throw new Error(`terser minification failed: ${err.message}`);
    }
    return result.code;
  }
  throw new Error(`Unsupported asset type: ${type}`);
}

const manifest = {
  generated_by: relative(repoRoot, fileURLToPath(import.meta.url)),
  assets: {},
};

for (const asset of assets) {
  const inputPath = path.join(repoRoot, asset.source);
  const outputPath = path.join(repoRoot, asset.target);
  const source = fs.readFileSync(inputPath, 'utf8');
  assertBrandKitFallback(source, asset.source);
  let minified;
  try {
    minified = await minify(source, asset.type);
  } catch (err) {
    throw new Error(`Failed to minify ${asset.source}: ${err.message}`);
  }
  const output = `${minified}\n`;
  const hash = sha256(output);

  fs.mkdirSync(dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, output, 'utf8');

  manifest.assets[asset.source.replace(/^static\//, '')] = {
    file: asset.target.replace(/^static\//, ''),
    hash,
    bytes_before: Buffer.byteLength(source),
    bytes_after: Buffer.byteLength(output),
  };
}

const manifestPath = path.join(repoRoot, 'static/assets/dashboard-manifest.json');
fs.mkdirSync(dirname(manifestPath), { recursive: true });
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');

for (const [source, entry] of Object.entries(manifest.assets)) {
  const saved = entry.bytes_before - entry.bytes_after;
  const pct = ((saved / entry.bytes_before) * 100).toFixed(1);
  console.log(`${source} -> ${entry.file}?v=${entry.hash} (${saved} bytes, ${pct}% smaller)`);
}
