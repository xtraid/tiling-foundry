import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';

const root = resolve(process.argv[2] || 'build/solver-web/package');
const {default: createModule} = await import(pathToFileURL(root + '/foundry.mjs'));
const {prepare, checkAssignments} = await import(pathToFileURL(root + '/prepare.mjs'));
const module = await createModule();
const offsets = [[0,-1],[1,0],[0,1],[-1,0]];

function brute(data) {
  const results = new Set(), placed = {};
  const visit = index => {
    if (index === data.cells.length) {
      results.add(JSON.stringify(data.cells.map(c => placed[c.id])));
      return;
    }
    const cell = data.cells[index], [x,y] = cell.id.split(',').map(Number);
    for (const tile of data.tiles) {
      if (cell.fixed && tile.some((v,d) => v !== cell.fixed[d])) continue;
      if (cell.required.some((v,d) => v !== null && tile[d] !== v)) continue;
      if (offsets.some(([dx,dy],d) => {
        const other = placed[`${x+dx},${y+dy}`];
        return other && tile[d] !== other[(d+2)%4];
      })) continue;
      placed[cell.id] = tile;
      visit(index+1);
      delete placed[cell.id];
    }
  };
  visit(0);
  return [...results].sort();
}

async function enumerate(data, pause) {
  const prepared = prepare(data), pointers = [], results = [];
  const allocate = array => {
    const pointer = module._malloc(array.byteLength);
    pointers.push(pointer);
    module.HEAPU8.set(new Uint8Array(array.buffer),pointer);
    return pointer;
  };
  module.onSolution = domains => {
    const assigned = Object.fromEntries([...prepared.indices].map(([id,index]) =>
      [id,31-Math.clz32(module.HEAPU32[(domains>>>2)+index])]));
    checkAssignments(prepared,assigned);
    results.push(JSON.stringify(data.cells.map(c => data.tiles[assigned[c.id]])));
    return pause ? 1 : 0;
  };
  module.onWait = async () => { await new Promise(r => setTimeout(r,5)); return 1; };
  try {
    const args = [prepared.width,prepared.height,allocate(prepared.active),
      allocate(prepared.boundary),allocate(prepared.edges),prepared.tiles.length,
      allocate(prepared.domains),Number(prepared.solver==='reference')];
    assert.equal(await module.ccall('foundry_enumerate','number',Array(8).fill('number'),args,{async:true}),0);
    assert.equal(new Set(results).size,results.length,'No repeated edge configurations');
    return results.sort();
  } finally { pointers.forEach(p => module._free(p)); }
}

const instance = (tiles,width=2,height=2) => ({geometry:'square',palette:['#ffffff','#000000'],tiles,
  cells:Array.from({length:width*height},(_,i)=>({id:`${i%width},${Math.floor(i/width)}`,required:[null,null,null,null]}))});
let seed = 17821;
const random = n => { seed=(Math.imul(seed,1664525)+1013904223)>>>0; return Math.floor(seed/4294967296*n); };
for(let i=0;i<100;i++) {
  const data = instance(Array.from({length:1+random(4)},()=>Array.from({length:4},()=>random(2))));
  for (const cell of data.cells) cell.required=Array.from({length:4},()=>[null,null,0,1][random(4)]);
  if(i%3===0)data.cells[0].fixed=data.tiles[0];
  const expected=brute(data);
  for (const solver of ['optimized','reference']) assert.deepEqual(await enumerate({...data,solver}),expected);
}
for (const solver of ['optimized','reference']) {
  const data=instance([[0,0,0,0],[1,1,1,1],[0,0,0,0]],1,1);
  data.solver=solver;
  data.cells.push({id:'-3,-3',required:[null,null,null,null]});
  assert.deepEqual(await enumerate(data,true),brute(data),'Asyncify pause preserves native enumeration');
  const bit31=instance(Array.from({length:32},(_,n)=>[n%16,Math.floor(n/16),0,0]),1,1);
  bit31.solver=solver;
  bit31.palette=Array(16).fill('#ffffff');
  bit31.cells[0].fixed=bit31.tiles[31];
  assert.deepEqual(await enumerate(bit31),brute(bit31),'Bit 31 and symbolic equal-RGB colors');
  const hole=instance([[0,0,0,0]],3,3);
  hole.cells=hole.cells.filter(c=>c.id!=='1,1');
  assert.deepEqual(await enumerate({...hole,solver}),brute(hole));
}
assert.throws(()=>prepare({...instance([[0,0,0,0]]),geometry:'hex-flat'}));
assert.throws(()=>prepare({...instance([[0,0,0,0]]),timeout_seconds:NaN}));
const duplicate=instance([[0,0,0,0]],1,1);
duplicate.cells.push({id:'00,0',required:[null,null,null,null]});
assert.throws(()=>prepare(duplicate),/duplicate/);
console.log('PASS: C reference and optimized Wasm vs exhaustive enumeration on 100 instances, async pause, duplicates, disconnected regions, holes, bit 31, validation.');
