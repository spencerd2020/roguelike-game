// usage: node shot.js <url> <out-prefix> [actions json]
const { chromium } = require('playwright');
(async () => {
  const [url, out, acts] = process.argv.slice(2);
  const proxy = undefined;
  const b = await chromium.launch({ proxy, args: ['--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1100, height: 660 }, ignoreHTTPSErrors: true });
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('console', m.type(), m.text().slice(0, 300)); });
  p.on('pageerror', e => console.log('pageerror', e.message));
  await p.route(/cdn\.jsdelivr\.net\/npm\/three@0\.128\.0\/.*\/([A-Za-z.]+\.js)$/, (route, req) => {
    const f = req.url().split('/').pop();
    route.fulfill({ path: __dirname + '/vendor/' + f, contentType: 'application/javascript' });
  });
  await p.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ body: '', contentType: 'text/css' }));
  await p.goto(url);
  await p.waitForFunction(() => document.getElementById('status').hidden || /failed/.test(document.getElementById('status').textContent), null, { timeout: 240000 }).catch(e => console.log('timeout waiting'));
  console.log('status:', await p.evaluate(() => document.getElementById('status').textContent));
  const list = acts ? JSON.parse(acts) : [['wait', 1500], ['shot', 'walk']];
  for (const [a, v] of list) {
    if (a === 'wait') await p.waitForTimeout(v);
    else if (a === 'js') await p.evaluate(v);
    else if (a === 'click') await p.click(v);
    else if (a === 'shot') { await p.waitForTimeout(800); await p.screenshot({ path: `${out}_${v}.png`, timeout: 240000 }); }
  }
  console.log('stats', await p.evaluate(() => [document.getElementById('s-tris').textContent, document.getElementById('s-calls').textContent, document.getElementById('s-fps').textContent, document.getElementById('s-comp').textContent, document.getElementById('s-bld').textContent].join(' | ')));
  await b.close();
})();
