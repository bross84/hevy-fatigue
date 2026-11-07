const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('static/index.html', 'utf8');
const diagnostic = fs.readFileSync('static/diagnostic.html', 'utf8');
for (const [name, html] of [['dashboard', page], ['diagnostic', diagnostic]]) {
  for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\b[^>]*>/gi)) new vm.Script(match[1], {filename:name});
}
function extract(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, name);
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  return end < 0 ? rest : rest.slice(0, end + 1);
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {innerHTML:'', style:{}, querySelector:()=>null, getContext:()=>({})});
  return elements.get(id);
};
const context = vm.createContext({
  document:{getElementById:element},
  REC_META:{continue:{label:'Continue'}},
  _safePatternStatus:()=>Object.fromEntries(['knee','hip','push','pull'].map(p=>[p,{load_dots:1,soreness_dots:1}])),
  _safeJointAdvisory:()=>({upper:{level:'none'},lower:{level:'none'}}),
  themeColors:()=>({accent:'#3772ff',card:'#fff'}),
  _weekdayLabel:x=>x, _dateLabel:x=>x,
  _destroyTodayReadinessChart:()=>{},
  _todayReadinessBandsPlugin:()=>({}),
  _trendChartBaseOptions:()=>({plugins:{tooltip:{}},scales:{x:{ticks:{}},y:{ticks:{}}}}),
  Chart:function(ctx,config) {this.config=config;context.lastChart=config;},
});
for (const name of ['escHtml','_stateClass','_safePatternStatus','_safeJointAdvisory','_renderTodayCards','renderTodayReadinessChart']) vm.runInContext(extract(page,name),context);
const fallback = {training_state:'insufficient_data',training_state_label:'Continue Training as Normal',
  training_state_detail:'Insufficient data to recommend a change.', data_sufficient:false,
  combined_score:2, smoothed_score:2};
context._renderTodayCards({today:{checkin_exists:true,recommendation_v2:fallback}},0);
let html=element('dashboard-readiness-card').innerHTML;
assert.ok(!html.includes('Continue Training as Normal'));
assert.ok(!html.includes('Legacy rule output'));
assert.ok(!html.includes('See your AI training recommendation below.'));
assert.match(html, /<div class="readiness-rec">\s*<section id="daily-coach-review"/);
assert.ok(html.includes('Combined'));
assert.ok(html.includes('readiness-score">—'));
assert.ok(!html.includes('today-state-large_increase'));
context._renderTodayCards({today:{checkin_exists:true,recommendation_v2:{...fallback,
  training_state:'continue',training_state_label:'Continue',data_sufficient:true,
  combined_score:5.52,smoothed_score:9.89}}},0);
assert.ok(element('dashboard-readiness-card').innerHTML.includes('readiness-score">9.9'));
context.renderTodayReadinessChart([
  {date:'2026-10-28',combined_score:2,smoothed_score:2,data_sufficient:false},
  {date:'2026-10-29',combined_score:null,smoothed_score:null,data_sufficient:false},
  {date:'2026-10-30',combined_score:5.52,smoothed_score:9.89,data_sufficient:true},
]);
assert.equal(JSON.stringify(context.lastChart.data.datasets[0].data),JSON.stringify([null,null,9.89]));
assert.equal(context.lastChart.data.datasets[0].spanGaps,false);
assert.equal(JSON.stringify(context.lastChart.data.datasets[1].data),JSON.stringify([2,null,5.52]));
assert.equal(context.lastChart.options.scales.y.min,0);
assert.equal(context.lastChart.options.scales.y.max,20);
assert.ok(!element('today-readiness-trend-card').innerHTML.includes('Optimal'));
context.renderTodayReadinessChart([{date:'2026-10-30',combined_score:5.52,smoothed_score:9.89,data_sufficient:true,
  historical_range:{sufficient:true,lower:4,upper:9,observations:30,window_days:84}}]);
assert.ok(element('today-readiness-trend-card').innerHTML.includes('Usual range 4.0–9.0'));
assert.ok(element('today-readiness-trend-card').innerHTML.includes('30 valid observations'));
// The shaded range is point-specific, and missing history is never painted as zero.
const drawings=[];
const bands=vm.createContext({});vm.runInContext(extract(page,'_todayReadinessBandsPlugin'),bands);
bands._todayReadinessBandsPlugin([{historical_range:{sufficient:true,lower:4,upper:9}},{historical_range:{sufficient:false}}]).beforeDatasetsDraw({
  ctx:{save(){},restore(){},fillRect(...args){drawings.push(args);}},chartArea:{left:0,right:100},
  scales:{x:{getPixelForValue:i=>i*100},y:{getPixelForValue:y=>200-y*10}}});
assert.deepEqual(drawings,[[0,110,50,50]]);
const helpers=diagnostic.slice(diagnostic.indexOf('    function escHtml('),diagnostic.indexOf('    async function loadAndRender('));
const diag=vm.createContext({formatDate:x=>x});
vm.runInContext(helpers,diag);
html=diag.renderEngineSnapshot({checkin_exists:false,recommendation_v2:fallback});
assert.ok(html.includes('Continue Training as Normal'));
assert.ok(!html.includes('neutral fallback'));
console.log('UI checks passed: fallback label, unavailable score, smoothed dashboard score, chart gaps, diagnostics, script syntax.');

for (let rating=0;rating<=4;rating++) {
  const labels=['None','Mild','Moderate','Significant','Severe'];
  const profile={load_signal:.5,load_dots:3,load_data_sufficient:true,
    soreness_rating:rating,soreness_signal:rating/4,soreness_dots:rating+1,
    combined_signal:.8,dots_filled:5,data_sufficient:true};
  context._renderTodayCards({today:{checkin_exists:true,recommendation_v2:{...fallback,pattern_status:{knee:profile}}}},0);
  const patternHtml=element('dashboard-pattern-card').innerHTML;
  const knee=patternHtml.slice(patternHtml.indexOf('pattern-gauge-name">Knee'),patternHtml.indexOf('pattern-gauge-name">Hip'));
  assert.ok(knee.includes(labels[rating]),`Soreness ${rating} preserves its own label`);
  assert.ok(knee.includes(`width:${(rating/4*100).toFixed(1)}%`));
  assert.ok(knee.includes('Trend'));
}
context._renderTodayCards({today:{checkin_exists:false,recommendation_v2:{...fallback,pattern_status:{knee:{
  load_signal:.5,load_dots:3,load_data_sufficient:true,soreness_rating:null,data_sufficient:false,
}}}}},0);
const missing=element('dashboard-pattern-card').innerHTML;
assert.ok(missing.includes('width:50.0%'));
assert.ok(missing.includes('pattern-gauge-status-pending">—'));
console.log('Pattern UI checks passed: exact 0-4 labels, continuous fills, missing observations, persistent training load.');
