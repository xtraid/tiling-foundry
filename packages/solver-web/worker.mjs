import createModule from './foundry.mjs';
import {prepare, checkAssignments} from './prepare.mjs';

let resume = null, started = false;
self.onmessage = ({data}) => {
  if (data.type === 'start' && !started) {
    started = true;
    run(data.payload).catch(error => self.postMessage({status: 'error', exact: false, message: error.message}));
  } else if (data.type === 'resume' && resume && ['next', 'count'].includes(data.action)) {
    const accept = resume;
    resume = null;
    accept(data);
  }
};

async function run(payload) {
  const prepared = prepare(payload);
  const module = await createModule();
  let count = 0n, generation = 0, mode = prepared.mode, assignments = null;
  let metrics = {}, lastEmit = 0, pausedAt = 0, pausedTime = 0;
  const began = performance.now();
  const publish = (status, exact = false) => self.postMessage({
    status, exact, count: count.toString(), assignments, metrics, generation,
    elapsed_ms: Math.round((performance.now() - began - pausedTime) * 100) / 100,
  });
  const snapshot = pointer => {
    const result = {};
    for (const [id, index] of prepared.indices) {
      const mask = module.HEAPU32[(pointer >>> 2) + index];
      if (!mask || (mask & (mask - 1)) !== 0) throw Error('Dominio non singleton nella soluzione.');
      result[id] = 31 - Math.clz32(mask);
    }
    return checkAssignments(prepared, result);
  };
  module.onSolution = (domains, counters) => {
    count++;
    const now = performance.now();
    if (mode !== 'step' && count !== 1n && now - lastEmit < 150) return 0;
    // Copy only published snapshots; native Foundry verifies every witness.
    if (mode === 'step' || assignments === null) assignments = snapshot(domains);
    const values = new DataView(module.HEAPU8.buffer);
    metrics = Object.fromEntries(['nodes', 'backtracks', 'reductions'].map((key, i) =>
      [key, values.getBigUint64(counters + i * 8, true).toString()]));
    lastEmit = now;
    if (mode === 'step') {
      pausedAt = now;
      publish('paused');
      return 1;
    }
    publish('running');
    return 2;
  };
  module.onWait = async action => {
    if (action === 1) {
      const command = await new Promise(resolve => { resume = resolve; });
      generation = command.generation;
      mode = command.action === 'count' ? 'count' : 'step';
      pausedTime += performance.now() - pausedAt;
      publish('running');
    } else {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    return 1;
  };
  const allocations = [];
  const allocate = array => {
    const pointer = module._malloc(array.byteLength);
    if (!pointer) throw Error('Memoria insufficiente per la ricerca.');
    allocations.push(pointer);
    module.HEAPU8.set(new Uint8Array(array.buffer, array.byteOffset, array.byteLength), pointer);
    return pointer;
  };
  publish('running');
  try {
    const args = prepared.graph ? [prepared.records.size, prepared.sides, allocate(prepared.neighbors),
      allocate(prepared.neighborSides), allocate(prepared.boundary), allocate(prepared.edges),
      prepared.tiles.length, allocate(prepared.domains), Number(prepared.solver === 'reference')] : [prepared.width, prepared.height, allocate(prepared.active),
      allocate(prepared.boundary), allocate(prepared.edges), prepared.tiles.length,
      allocate(prepared.domains), Number(prepared.solver === 'reference')];
    const status = await module.ccall(prepared.graph ? 'foundry_enumerate_graph' : 'foundry_enumerate', 'number',
      Array(args.length).fill('number'), args, {async: true});
    if (status !== 0) throw Error('Il motore ha interrotto la ricerca senza esaurirla.');
    publish('complete', true);
  } finally {
    allocations.forEach(pointer => module._free(pointer));
  }
}
