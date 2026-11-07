const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx=vm.createContext({});
vm.runInContext(fs.readFileSync('rackbook/static/app-menu.js','utf8')+';this.menu=AppMenu;',ctx);
const groups=JSON.parse(JSON.stringify(ctx.menu.groups.map(g=>({name:g.name,items:g.items.map(i=>({label:i.label,href:i.href}))}))));

// The dashboard keeps its own sidebar (tab buttons and badges); it must list exactly the same menu.
const html=fs.readFileSync('static/index.html','utf8');
const side=html.slice(html.indexOf('<aside id="hostSidebar"'),html.indexOf('</aside>',html.indexOf('<aside id="hostSidebar"')));
const host=[];
for(const m of side.matchAll(/<span class="host-nav-group">([^<]*)<\/span>|<button[^>]*data-tab="([^"]+)"[^>]*>([^<]*)|<a href="([^"]+)">([^<]*)<\/a>/g)){
  if(m[1]!==undefined)host.push({name:m[1],items:[]});
  else if(m[2]!==undefined)host.at(-1).items.push({label:m[3].trim(),href:m[2]==='dashboard'?'/':'/#'+m[2]});
  else host.at(-1).items.push({label:m[5].trim(),href:m[4]});
}
assert.deepEqual(host,groups,'dashboard sidebar matches the shared menu definition');

// Every logger page draws its menu from the shared script; none keeps a hand-written copy.
const pages={'log.html':'sidebar','mesocycles.html':'bar','recent.html':'bar','progress.html':'bar','stress.html':'bar','rpe_charts.html':'bar','trial.html':'bar'};
for(const [file,variant] of Object.entries(pages)){
  const text=fs.readFileSync('rackbook/'+file,'utf8');
  const navs=[...text.matchAll(/<nav class="app-nav"[\s\S]*?<\/nav>/g)].map(m=>m[0]);
  assert.equal(navs.length,1,file+' has one menu');
  assert.ok(navs[0].includes('data-app-menu="'+variant+'"'),file+' uses the '+variant+' menu');
  assert.ok(!navs[0].includes('<a '),file+' has no hand-written menu links');
  assert.ok(/<script src="\/training\/static\/app-menu\.js(\?v=\d+)?"><\/script>/.test(text),file+' loads the shared menu');
}

// Model trial stays out of the main navigation.
assert.ok(!JSON.stringify(groups).includes('/training/trial'));
console.log('App menu: one shared definition, dashboard sidebar identical, seven logger pages use it, Model trial excluded.');
