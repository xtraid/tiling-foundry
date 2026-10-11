import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';

const root = resolve(process.argv[2] || 'build/solver-web/package');
const {default: createModule} = await import(pathToFileURL(root + '/foundry.mjs'));
const {prepare, checkAssignments} = await import(pathToFileURL(root + '/prepare.mjs'));
const module = await createModule();
// Independent polygon edge matching, not the package's lattice-neighbor table.
function polygon(data, id) {
  const [i,j,h=0]=id.split(',').map(Number), g=data.geometry;
  if(g==='square') return [[i,j],[i+1,j],[i+1,j+1],[i,j+1]];
  if(g.startsWith('tri')) {
    const x=i+j/2,y=j*Math.sqrt(3)/2;
    const p=h?[[x+1.5,y+Math.sqrt(3)/2],[x+.5,y+Math.sqrt(3)/2],[x+1,y]]
      :[[x,y],[x+1,y],[x+.5,y+Math.sqrt(3)/2]];
    return g==='tri-side'?p.map(([x,y])=>[-y,x]):p;
  }
  const flat=g==='hex-flat',x=flat?1.5*i:Math.sqrt(3)*(i+j/2),y=flat?Math.sqrt(3)*(j+i/2):1.5*j;
  return Array.from({length:6},(_,d)=>[x+Math.cos((flat?0:-Math.PI/2)+d*Math.PI/3),y+Math.sin((flat?0:-Math.PI/2)+d*Math.PI/3)]);
}
function edgeKeys(data,id) {
  const p=polygon(data,id).map(p=>p.map(x=>Math.round(x*1e5)).join(','));
  return p.map((v,d)=>[v,p[(d+1)%p.length]].sort().join('|'));
}

function brute(data) {
  const results = new Set(), placed = {};
  const keys = Object.fromEntries(data.cells.map(c=>[c.id,edgeKeys(data,c.id)]));
  const visit = index => {
    if (index === data.cells.length) {
      results.add(JSON.stringify(data.cells.map(c => placed[c.id])));
      return;
    }
    const cell = data.cells[index], [x,y] = cell.id.split(',').map(Number);
    for (const tile of data.tiles) {
      if (cell.fixed && tile.some((v,d) => v !== cell.fixed[d])) continue;
      if (cell.required.some((v,d) => v !== null && tile[d] !== v)) continue;
      if (Object.entries(placed).some(([id,other])=>keys[cell.id].some((key,d)=>{
        const side=keys[id].indexOf(key);return side>=0 && tile[d]!==other[side];
      }))) continue;
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
    const args = prepared.graph ? [prepared.records.size,prepared.sides,allocate(prepared.neighbors),
      allocate(prepared.neighborSides),allocate(prepared.boundary),allocate(prepared.edges),
      prepared.tiles.length,allocate(prepared.domains),Number(prepared.solver==='reference')] : [prepared.width,prepared.height,allocate(prepared.active),
      allocate(prepared.boundary),allocate(prepared.edges),prepared.tiles.length,
      allocate(prepared.domains),Number(prepared.solver==='reference')];
    assert.equal(await module.ccall(prepared.graph?'foundry_enumerate_graph':'foundry_enumerate','number',Array(args.length).fill('number'),args,{async:true}),0);
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

for(const geometry of ['tri-up','tri-side','hex-flat','hex-point']) {
  const sides=geometry.startsWith('tri')?3:6;
  const ids=sides===3?['-1,0,0','-1,0,1','0,0,0','0,0,1','0,-1,1']:['-1,0','0,0','0,1','1,0'];
  const base={geometry,palette:['#ffffff','#000000'],tiles:[Array(sides).fill(0),Array(sides).fill(1),Array(sides).fill(0)],
    cells:ids.map(id=>({id,required:Array(sides).fill(null)}))};
  for(const solver of ['optimized','reference']) {
    assert.deepEqual(await enumerate({...base,solver},true),brute(base));
    const disconnected={...base,solver,cells:[base.cells[0],{id:sides===3?'9,9,1':'9,9',required:Array(sides).fill(null)}]};
    assert.equal((await enumerate(disconnected)).length,4);
    const bit31={...base,solver,palette:Array(16).fill('#ffffff'),
      tiles:Array.from({length:32},(_,n)=>[n%16,Math.floor(n/16),...Array(sides-2).fill(0)]),cells:[base.cells[0]]};
    bit31.cells=[{...base.cells[0],fixed:bit31.tiles[31]}];
    assert.deepEqual(await enumerate(bit31),brute(bit31));
  }
  for(let trial=0;trial<100;trial++) {
    const data={...base,tiles:Array.from({length:1+random(5)},()=>Array.from({length:sides},()=>random(2))),
      cells:base.cells.map(c=>({...c,required:Array.from({length:sides},()=>random(5)===0?random(2):null)}))};
    if(trial%3===0)data.cells[0].fixed=data.tiles[random(data.tiles.length)];
    const expected=brute(data);
    for(const solver of ['optimized','reference'])assert.deepEqual(await enumerate({...data,solver}),expected,geometry+' trial '+trial);
  }
  assert.throws(()=>prepare({...base,cells:[{...base.cells[0],id:'0,0,2'}]}));
  assert.throws(()=>checkAssignments(prepare(base),{}));
}
console.log('PASS: all four triangular/hexagonal variants, 400 random instances against independent polygon oracle, both C engines, pause, fixed tiles, duplicates, disconnected cells and bit 31.');
