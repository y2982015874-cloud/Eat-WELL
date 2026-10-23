/**
 * frontend_render_check.js —— 前端渲染回归检查（第四阶段测试资产）
 *
 * 作用：用**真实后端响应**驱动 web/index.html 的真实渲染函数，检测
 *      "前端读取了后端未返回的字段"导致的渲染中断（例如 t.weight_g）。
 *
 * 用法：node tests/frontend_render_check.js <response.json> [<response2.json> ...]
 * 退出码：0 = 所有响应的五个区块均渲染成功；1 = 存在渲染中断或空白区块；2 = 环境错误
 *
 * 说明：不依赖浏览器；用最小 DOM stub 复刻 run() 的调用顺序
 *      renderDet -> renderCls -> renderMeal -> renderTar -> renderAlert（连续调用、无逐个 try）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('未能在 web/index.html 中找到 <script> 段'); process.exit(2); }

/* ---- 最小 DOM stub ---- */
const els = new Map();
function mkEl() {
  return { innerHTML: '', textContent: '', className: '', hidden: false, style: { cssText: '' },
           classList: { toggle() {}, add() {}, remove() {} },
           querySelectorAll() { return []; }, appendChild() {}, children: [],
           dataset: {}, value: '', src: '' };
}
global.document = {
  getElementById(id) { if (!els.has(id)) els.set(id, mkEl()); return els.get(id); },
  createElement: () => mkEl(),
};
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({ ready: true }) });
global.alert = () => {};

/* ---- 执行页面脚本，导出渲染函数 ---- */
eval(m[1] + '\n;globalThis.__F={renderDet,renderCls,renderMeal,renderTar,renderAlert};');
// 注意：直接 eval 会把页面里的函数声明泄漏到本模块作用域，故用别名 F 引用，避免重复声明
const F = globalThis.__F;

const SECTIONS = {
  detBox:  '第2节 检测结果',
  clsBox:  '第3节 分类Top5',
  mealBox: '第6节 营养计算',
  tarBox:  '第7节 每日目标',
  alertBox:'第8节 预警',
};

const files = process.argv.slice(2);
if (!files.length) { console.error('用法: node tests/frontend_render_check.js <response.json> ...'); process.exit(2); }

let fail = 0;
for (const f of files) {
  const d = JSON.parse(fs.readFileSync(f, 'utf8'));
  els.clear();
  const done = [];
  let err = null;
  try {
    F.renderDet(d);   done.push('renderDet');
    F.renderCls(d);   done.push('renderCls');
    F.renderMeal(d);  done.push('renderMeal');
    F.renderTar(d);   done.push('renderTar');
    F.renderAlert(d); done.push('renderAlert');
  } catch (e) { err = e; }

  const g = id => ((els.get(id) || {}).innerHTML || '');
  const blank = Object.keys(SECTIONS).filter(k => g(k).length === 0);
  const ok = !err && blank.length === 0;

  console.log(`\n--- ${path.basename(f)} ---`);
  if (err) {
    console.log(`  渲染中断: ${err.constructor.name}: ${err.message}`);
    console.log(`  中断前已完成: ${done.join(' -> ') || '(无)'}`);
  }
  for (const [k, label] of Object.entries(SECTIONS)) {
    console.log(`  ${label}: ${g(k).length} 字符${g(k).length === 0 ? '  ← 空白' : ''}`);
  }
  console.log(`  结论: ${ok ? 'PASS' : 'FAIL'}`);
  if (!ok) fail++;
}

console.log(`\n合计 ${files.length} 个响应，失败 ${fail} 个`);
process.exit(fail ? 1 : 0);
