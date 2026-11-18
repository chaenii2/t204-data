#!/usr/bin/env node
/* T204 구형 IE(IE11)용 ZIP 패키징
   사용: node package_zip_ie.js <빌드된 index.html> <출력 폴더>
   - JS: Babel로 ES5 변환 + 폴리필(core-js, regenerator, fetch, AbortController, DOM 보조)
   - CSS: 변수(var(--x)) 값으로 치환, inset·gap 풀어쓰기, -ms- 접두사
   - 글꼴: IE는 woff2·가변 글꼴 미지원 → 굵기별 정적 woff 6개
   - X-UA-Compatible IE=edge (호환성 보기 방지) */
const fs = require('fs'), path = require('path');
const babel = require('@babel/core');
const postcss = require('postcss');
const autoprefixer = require('autoprefixer');
const acorn = require('acorn');

const [src, outDir] = process.argv.slice(2);
const NM = path.join(__dirname, 'node_modules'); // 처음 한 번: cd scripts/ie && npm install
let h = fs.readFileSync(src, 'utf8');

// 1) :root 변수 수집
const vars = {};
const rootM = h.match(/:root\s*\{([^}]*)\}/);
if (rootM) for (const m of rootM[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);?/g)) vars[m[1]] = m[2].trim();
const subVars = s => s.replace(/var\((--[\w-]+)(?:\s*,\s*([^)]+))?\)/g, (all, k, d) => vars[k] || (d ? d.trim() : all));
const subInset = s => s.replace(/\binset\s*:\s*0(px)?\b/g, 'top:0;right:0;bottom:0;left:0');

// 2) 외부 글꼴 링크 제거
h = h.replace(/\s*<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>/g, '');

// 3) <style> 처리
const styleJobs = [];
h = h.replace(/<style([^>]*)>([\s\S]*?)<\/style>/g, (all, attrs, css) => {
  const key = `@@STYLE${styleJobs.length}@@`;
  styleJobs.push({ key, attrs, css });
  return key;
});
// 4) <script> 처리 (인라인만)
const scriptJobs = [];
h = h.replace(/<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g, (all, attrs, js) => {
  const key = `@@SCRIPT${scriptJobs.length}@@`;
  scriptJobs.push({ key, attrs, js });
  return key;
});
// 본문 마크업의 인라인 스타일
h = subInset(subVars(h));

(async () => {
  for (const j of styleJobs) {
    let css = subInset(subVars(j.css));
    css = css.replace(/(\.spon\{[^}]*?)gap:18px/, '$1').replace(/(#ctl\{[^}]*?)gap:6px/, '$1');
    css += '\n.spon>*+*{margin-left:18px}#ctl>*+*{margin-left:6px}';
    const r = await postcss([autoprefixer({ overrideBrowserslist: ['ie 11'], grid: false })]).process(css, { from: undefined });
    h = h.replace(j.key, () => `<style${j.attrs}>${r.css}</style>`);
  }
  for (const j of scriptJobs) {
    const ty = (j.attrs.match(/type=["']?([^"' >]+)/) || [])[1];
    if (ty && !/javascript|ecmascript/i.test(ty)) { h = h.replace(j.key, () => `<script${j.attrs}>${j.js}</script>`); continue; }
    let js = subInset(subVars(j.js));
    const out = babel.transformSync(js, {
      babelrc: false, configFile: false, sourceType: 'script', compact: false, comments: false,
      presets: [[require.resolve('@babel/preset-env'), { targets: { ie: '11' }, modules: false, useBuiltIns: false }]],
    }).code;
    acorn.parse(out, { ecmaVersion: 5 }); // ES5 문법만 남았는지 검증 (실패 시 예외)
    h = h.replace(j.key, () => `<script${j.attrs}>${out}</script>`);
  }

  // 5) 폴리필 + 글꼴 + 메타
  const poly = [
    fs.readFileSync(path.join(NM, 'core-js-bundle/minified.js'), 'utf8').replace(/\/\/# sourceMappingURL=.*$/m, ''),
    fs.readFileSync(path.join(NM, 'regenerator-runtime/runtime.js'), 'utf8'),
    fs.readFileSync(path.join(NM, 'whatwg-fetch/dist/fetch.umd.js'), 'utf8'),
    fs.readFileSync(path.join(NM, 'abortcontroller-polyfill/dist/umd-polyfill.js'), 'utf8'),
    `(function(){var E=Element.prototype;
if(window.NodeList&&!NodeList.prototype.forEach)NodeList.prototype.forEach=Array.prototype.forEach;
if(!E.matches)E.matches=E.msMatchesSelector||E.webkitMatchesSelector;
if(!E.closest)E.closest=function(s){var el=this;while(el&&el.nodeType===1){if(el.matches(s))return el;el=el.parentElement||el.parentNode;}return null;};
if(!E.remove)E.remove=function(){if(this.parentNode)this.parentNode.removeChild(this);};
var t=document.createElement('_');t.classList.toggle('c',false);
if(t.classList.contains('c')){var o=DOMTokenList.prototype.toggle;DOMTokenList.prototype.toggle=function(c,f){if(arguments.length>1&&this.contains(c)===!f)return o.call(this,c);if(arguments.length>1)return !!f;return o.call(this,c);};}
if(!window.performance||!performance.now){window.performance=window.performance||{};var s0=Date.now();performance.now=function(){return Date.now()-s0;};}
})();`,
  ].join('\n;\n');
  fs.mkdirSync(path.join(outDir, 'font'), { recursive: true });
  fs.mkdirSync(path.join(outDir, 'js'), { recursive: true });
  fs.writeFileSync(path.join(outDir, 'js/polyfill-ie11.js'), poly);
  const W = [400, 500, 600, 700, 800, 900];
  const faces = W.map(w => `@font-face{font-family:'Noto Sans KR';src:url('font/NotoSansKR-T204-${w}.woff') format('woff');font-weight:${w};font-style:normal}`).join('\n');
  for (const w of W) fs.copyFileSync(path.join(__dirname, `../../assets/font/NotoSansKR-T204-${w}.woff`), path.join(outDir, `font/NotoSansKR-T204-${w}.woff`));
  const head = `<meta http-equiv="X-UA-Compatible" content="IE=edge">\n` +
    `<meta name="viewport" content="width=1200,initial-scale=1,maximum-scale=1,user-scalable=no">\n` +
    `<meta http-equiv="Pragma" content="no-cache">\n<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n` +
    `<style>${faces}</style>\n<script src="js/polyfill-ie11.js"></script>\n<script>window.T204_TOPLEFT=true;</script>\n`;
  h = h.replace(/<meta name="viewport"[^>]*>\n?/, '');
  if (!/<meta charset/i.test(h)) throw new Error('charset meta 없음');
  h = h.replace(/(<meta charset[^>]*>)/i, `$1\n${head}`);
  // IE에는 document.fonts가 없음 → 글꼴이 늦게 로드된 뒤 숫자 폭 다시 맞춤
  h = h.replace(/<\/body>/i, `<script>(function(){function r(){try{if(window.fitNums)fitNums();}catch(e){}}var i,d=[500,1500,3000,6000];for(i=0;i<d.length;i++)setTimeout(r,d[i]);})();</script>\n</body>`);
  fs.writeFileSync(path.join(outDir, 'index.html'), h);
  const left = (h.replace(/data:[^"')]+/g, '').match(/var\(--|\binset\s*:|fonts\.googleapis/g) || []);
  console.log('ok', outDir, 'vars', Object.keys(vars).length, 'leftovers', left.length);
})().catch(e => { console.error(e); process.exit(1); });
