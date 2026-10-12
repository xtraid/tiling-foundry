import {prepare, limits, geometries} from './prepare.mjs';

const terminal = new Set(['complete', 'cancelled', 'timeout', 'expired', 'error']);
let manifestPromise;
export async function capabilities() {
  manifestPromise ??= fetch(new URL('./manifest.json', import.meta.url)).then(async response => {
    if (!response.ok) throw Error('Pacchetto solver non disponibile.');
    const manifest = await response.json();
    if (manifest.api_version !== 1) throw Error('Versione del pacchetto solver non compatibile.');
    return manifest;
  }).catch(error => { manifestPromise = null; throw error; });
  return {solver: 'optimized', solvers: ['optimized', 'reference'], runtime: 'wasm', geometries,
    enumeration: true, duplicate_tiles: 'collapsed', ...limits,
    engine: await manifestPromise};
}

export class Solver {
  constructor() { this.jobs = new Map(); }

  async start(payload) {
    const copy = structuredClone(payload);
    const {timeout, idleTimeout, solver} = prepare(copy);
    this.reap();
    if ([...this.jobs.values()].some(job => !terminal.has(job.result.status))) {
      throw Error('È già presente una ricerca. Premi Stop prima di avviarne un’altra.');
    }
    // Reserve the slot before awaiting the manifest to prevent concurrent starts.
    const id = crypto.randomUUID();
    const job = {worker: null, timer: null, generation: 0, timeout, idleTimeout, finished: null,
      result: {status: 'running', solver, runtime: 'wasm', count: '0', exact: false, generation: 0}};
    this.jobs.set(id, job);
    this.arm(job, timeout * 1000, 'timeout');
    try {
      const caps = await capabilities();
      if (terminal.has(job.result.status)) return {id, ...job.result};
      job.result.engine = caps.engine;
      const worker = new Worker(new URL('./worker.mjs', import.meta.url), {type: 'module'});
      job.worker = worker;
      worker.onmessage = ({data}) => {
        if (terminal.has(job.result.status) || data.generation != null && data.generation !== job.generation) return;
        if (data.status === 'error') { this.finish(job, 'error', data.message); return; }
        job.result = {...job.result, ...data};
        if (data.status === 'paused') this.arm(job, job.idleTimeout * 1000, 'expired');
        else if (terminal.has(data.status)) this.finish(job, data.status);
        // Progress does not reset the active deadline; resume() starts a segment.
      };
      worker.onerror = event => { event.preventDefault(); this.finish(job, 'error', event.message || 'Errore del Worker.'); };
      worker.onmessageerror = () => this.finish(job, 'error', 'Risposta del Worker non leggibile.');
      worker.postMessage({type: 'start', payload: copy});
      return {id, ...job.result};
    } catch (error) {
      this.finish(job, 'error', error.message);
      throw error;
    }
  }

  arm(job, milliseconds, outcome) {
    clearTimeout(job.timer);
    if (milliseconds === 0) { job.timer = null; return; }
    job.timer = setTimeout(() => this.finish(job, outcome), milliseconds);
  }

  finish(job, status, message) {
    if (job.finished !== null) return;
    clearTimeout(job.timer);
    job.worker?.terminate();
    job.worker = null;
    job.finished = Date.now();
    job.result = {...job.result, status, exact: status === 'complete' && job.result.exact === true};
    if (message) job.result.message = message;
  }

  get(id) {
    const job = this.jobs.get(id);
    if (!job) throw Error('Ricerca non trovata.');
    return structuredClone(job.result);
  }

  cancel(id) {
    const job = this.jobs.get(id);
    if (!job) throw Error('Ricerca non trovata.');
    if (!terminal.has(job.result.status)) this.finish(job, 'cancelled');
    return this.get(id);
  }

  resume(id, action) {
    const job = this.jobs.get(id);
    if (!job || job.result.status !== 'paused' || !['next', 'count'].includes(action)) {
      throw Error('La ricerca non è in attesa di una soluzione successiva.');
    }
    job.generation++;
    job.result = {...job.result, status: 'running', exact: false, generation: job.generation};
    this.arm(job, job.timeout * 1000, 'timeout');
    job.worker.postMessage({type: 'resume', action, generation: job.generation});
    return this.get(id);
  }

  reap() {
    for (const [id, job] of this.jobs) {
      if (job.finished !== null && Date.now() - job.finished > 600000) this.jobs.delete(id);
    }
  }

  close() {
    for (const job of this.jobs.values()) if (!terminal.has(job.result.status)) this.finish(job, 'cancelled');
  }
}
