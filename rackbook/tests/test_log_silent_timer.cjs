const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../log.html'), 'utf8');
assert.doesNotMatch(html, /AudioContext|audioSession|createOscillator/, 'The logger must not take over device audio');
let now = 1000, vibrations = 0, saves = 0;
const context = vm.createContext({Date:{now:()=>now},navigator:{vibrate(){vibrations++;}},
  restEnd:null,restTotal:0,restDone:false,restTimer:null,restKept:false,restExId:null,
  setInterval:()=>1,clearInterval(){},restRender(){},restSave(){saves++;}});
vm.runInContext(html.slice(html.indexOf('  function restNotify('), html.indexOf('  async function keepAwake(')), context);
vm.runInContext(html.slice(html.indexOf('  function restNudge('), html.indexOf('  $("restMinus").addEventListener')), context);
context.restStart(180,{id:'bench'});
assert.equal(context.restEnd,181000);assert.equal(context.restExId,'bench');
context.restNudge(15);assert.equal(context.restEnd,196000);assert.equal(context.restTotal,195);
context.restNudge(-15);assert.equal(context.restEnd,181000);
now=181000;context.restLoop();assert.equal(context.restDone,true);assert.equal(context.restEnd,null);
assert.equal(vibrations,1);context.restLoop();assert.equal(vibrations,1);
context.restStop();assert.equal(context.restDone,false);assert.ok(saves>=5);
console.log('Silent timer starts, adjusts, expires once and stops without taking device audio.');
