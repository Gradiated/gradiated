// Tiny static server for local testing: node serve.js  →  http://localhost:8080
const http = require('http');
const fs = require('fs');
const path = require('path');
const root = __dirname;
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.json': 'application/json' };
const SNAP_DIR = process.env.SNAP_DIR || '';
http.createServer((req, res) => {
  if (req.method === 'POST' && req.url.startsWith('/snap') && SNAP_DIR) {
    const name = (new URL(req.url, 'http://x').searchParams.get('name') || 'snap').replace(/[^a-z0-9_-]/gi, '');
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => { fs.writeFileSync(path.join(SNAP_DIR, name + '.png'), Buffer.concat(chunks)); res.writeHead(200); res.end('ok'); });
    return;
  }
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const file = path.normalize(path.join(root, p));
  if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(data);
  });
}).listen(8080, '127.0.0.1', () => console.log('serving', root, 'on http://localhost:8080'));
