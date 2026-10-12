// Usage: node tests/benchmark_solver_web.mjs OLD_PACKAGE NEW_PACKAGE
// Alternate modules within each sample to avoid systematic warmup/thermal bias.
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {prepare} from '../packages/solver-web/prepare.mjs';
const canonical=JSON.parse(await readFile(new URL('./web_yang_zhang.json',import.meta.url)));
const engines=[];
for(const directory of process.argv.slice(2)) {
  const {default:create}=await import(pathToFileURL(resolve(directory)+'/foundry.mjs'));
  engines.push({directory,module:await create(),cases:{}});
}
for(const [name,tiles] of [['yang-zhang-23',canonical],['32',Array.from({length:32},(_,i)=>[i%4,Math.floor(i/4)%2,0,Math.floor(i/8)])]]) {
  for(const solver of ['reference','optimized']) {
    const p=prepare({geometry:'square',palette:Array(16).fill('#ffffff'),tiles,solver,
      cells:Array.from({length:4},(_,i)=>({id:`${i%2},${Math.floor(i/2)}`,required:[null,null,null,null]}))});
    const runners=engines.map(engine=>{
      const module=engine.module,pointers=[];
      const alloc=a=>{const x=module._malloc(a.byteLength);pointers.push(x);module.HEAPU8.set(new Uint8Array(a.buffer),x);return x;};
      const args=[p.width,p.height,alloc(p.active),alloc(p.boundary),alloc(p.edges),tiles.length,alloc(p.domains),Number(solver==='reference')];
      let count=0;module.onSolution=()=>{count++;return 0;};
      const run=()=>{count=0;assert.equal(module._foundry_enumerate(...args),0);return count;};
      const expected=run();for(let i=0;i<200;i++)assert.equal(run(),expected);
      return {engine,run,pointers,expected,times:[]};
    });
    assert.ok(runners.every(r=>r.expected===runners[0].expected));
    for(let sample=0;sample<9;sample++)for(const r of sample%2?[...runners].reverse():runners) {
      const start=performance.now();for(let i=0;i<1000;i++)r.run();r.times.push(performance.now()-start);
    }
    for(const r of runners) {
      r.times.sort((a,b)=>a-b);
      r.engine.cases[name+' '+solver]={median_ms_per_1000:r.times[4],solutions:r.expected};
      r.pointers.forEach(x=>r.engine.module._free(x));
    }
  }
}
console.log(JSON.stringify(engines.map(({directory,cases})=>({directory,cases})),null,2));
if(engines.length===2)for(const key of Object.keys(engines[0].cases))
  console.log(key+': new/old '+(engines[1].cases[key].median_ms_per_1000/engines[0].cases[key].median_ms_per_1000).toFixed(3));
