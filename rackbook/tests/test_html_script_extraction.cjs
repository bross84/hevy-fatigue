const assert = require('node:assert/strict');
const vm = require('node:vm');
const inlineScriptMatches = require('./helpers/html-scripts.cjs');

const html = '<SCRIPT data-fixture="one">const first = 1;</SCRIPT>\n' +
  '<sCrIpT type="text/javascript">const second = 2;</ScRiPt >\n' +
  '<script>const third = 3;</script><scripty>not JavaScript</scripty>';
const bodies = [...inlineScriptMatches(html)].map(match => match[1]);
assert.deepEqual(bodies, ['const first = 1;', 'const second = 2;', 'const third = 3;']);
for (const source of bodies) new vm.Script(source);
// An uppercase script containing invalid syntax must fail, not disappear.
assert.throws(() => {
  for (const match of inlineScriptMatches('<SCRIPT>const = ;</SCRIPT>')) new vm.Script(match[1]);
}, SyntaxError);
console.log('HTML script extraction: mixed-case tags, closing whitespace, tag boundaries and syntax failures passed.');
