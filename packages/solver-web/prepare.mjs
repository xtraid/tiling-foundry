/* Input validation and independent witness checking. No search implementation. */
export const limits = Object.freeze({
  max_tiles: null, max_used_colors: 65536, max_cells: 65536, max_area: null,
  max_palette: 65536, default_timeout_seconds: 600, max_timeout_seconds: 2147483,
  default_idle_timeout_seconds: 0, max_memory_bytes: 2147483648,
});
export const geometries = ['square', 'tri-up', 'tri-side', 'hex-flat', 'hex-point'];
const offsets = [[0, -1], [1, 0], [0, 1], [-1, 0]];

// Lattice coordinates are an input adapter only. The C core receives cell/side arcs.
export function adjacent(geometry, id) {
  const [x, y, half] = id.split(',').map(Number);
  if (geometry === 'square') return offsets.map(([dx,dy],d) => [`${x+dx},${y+dy}`, (d+2)%4]);
  if (geometry.startsWith('tri')) return [
    [`${x},${y+(half ? 1 : -1)},${1-half}`,0],
    [`${x},${y},${1-half}`,1],
    [`${x+(half ? 1 : -1)},${y},${1-half}`,2],
  ];
  const steps = geometry === 'hex-flat'
    ? [[1,0],[0,1],[-1,1],[-1,0],[0,-1],[1,-1]]
    : [[1,-1],[1,0],[0,1],[-1,1],[-1,0],[0,-1]];
  return steps.map(([dx,dy],d) => [`${x+dx},${y+dy}`, (d+3)%6]);
}

export function prepare(data) {
  if (!data || !geometries.includes(data.geometry)) throw Error('Geometria non supportata.');
  let graph = data.geometry !== 'square' || data.tiles?.length > 32;
  const triangle = data.geometry.startsWith('tri');
  const sides = triangle ? 3 : data.geometry.startsWith('hex') ? 6 : 4;
  const {palette, tiles, cells} = data;
  if (!Array.isArray(palette) || !palette.length || palette.length > limits.max_palette ||
      !palette.every(c => typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c))) {
    throw Error('Palette non valida.');
  }
  function edges(value, nullable = false) {
    if (!Array.isArray(value) || value.length !== sides || !value.every(v =>
      (nullable && v === null) || (Number.isInteger(v) && v >= 0 && v < palette.length))) {
      throw Error('Una tessera o un vincolo contiene lati non validi.');
    }
    return value;
  }
  if (!Array.isArray(tiles) || !tiles.length) {
    throw Error('Il solver richiede almeno una tessera.');
  }
  tiles.forEach(t => edges(t));
  if (!Array.isArray(cells) || !cells.length || cells.length > limits.max_cells) {
    throw Error('La regione deve contenere da 1 a 65536 celle.');
  }
  const timeout = data.timeout_seconds ?? limits.default_timeout_seconds;
  const idleTimeout = data.idle_timeout_seconds ?? limits.default_idle_timeout_seconds;
  if ([timeout, idleTimeout].some(t => typeof t !== 'number' || !Number.isFinite(t) || t < 0 || t > limits.max_timeout_seconds)) {
    throw Error('Tempo limite non valido (0 = senza scadenza; massimo 2147483 secondi).');
  }
  const mode = data.enumeration_mode ?? 'step';
  if (!['step', 'count'].includes(mode)) throw Error('Modalità di enumerazione non valida.');
  const solver = data.solver ?? 'optimized';
  if (!['optimized', 'reference'].includes(solver)) throw Error('Solver non supportato.');
  const records = new Map();
  const used = new Set(tiles.flat());
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const cell of cells) {
    if (!cell || typeof cell.id !== 'string' || !(triangle ? /^-?\d{1,7},-?\d{1,7},[01]$/ : /^-?\d{1,7},-?\d{1,7}$/).test(cell.id)) {
      throw Error('Coordinate non valide.');
    }
    const [x, y] = cell.id.split(',').map(Number);
    const key = triangle ? `${x},${y},${cell.id.split(',')[2]}` : `${x},${y}`;
    if (Math.abs(x) > 1000000 || Math.abs(y) > 1000000 || cell.id !== key || records.has(key)) {
      throw Error('Coordinate duplicate o fuori intervallo.');
    }
    edges(cell.required, true);
    if (cell.fixed != null) edges(cell.fixed);
    cell.required.forEach(v => { if (v !== null) used.add(v); });
    cell.fixed?.forEach(v => used.add(v));
    records.set(key, {...cell, x, y});
    x0 = Math.min(x0, x); x1 = Math.max(x1, x);
    y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const width = x1 - x0 + 1, height = y1 - y0 + 1;
  const wide = used.size > 16;
  graph ||= wide || cells.length > 4096 || width * height > 16384;
  const area = graph ? cells.length : width * height;
  if (used.size > limits.max_used_colors) throw Error('Il solver supporta al massimo 65536 colori usati.');
  // Colors are symbolic palette indices. Equal RGB values remain distinct.
  const remap = new Map([...used].sort((a, b) => a - b).map((v, i) => [v, i]));
  const ColorArray = wide ? Uint32Array : Uint8Array;
  const active = new Uint8Array(area), boundary = new ColorArray(area * sides).fill(wide ? 0xffffffff : 255);
  const words = Math.ceil(tiles.length / 32);
  const domains = new Uint32Array(area * words), indices = new Map();
  const neighbors = new Int32Array(area * sides).fill(-1);
  const neighborSides = new Uint8Array(area * sides);
  for (const cell of records.values()) indices.set(cell.id, graph ? indices.size : (cell.y-y0)*width+cell.x-x0);
  for (const cell of records.values()) {
    const index = indices.get(cell.id);
    indices.set(cell.id, index);
    active[index] = 1;
    tiles.forEach((tile, t) => {
      if ((!cell.fixed || tile.every((v, d) => v === cell.fixed[d])) &&
          cell.required.every((v, d) => v === null || tile[d] === v)) {
        domains[index * words + Math.floor(t / 32)] |= 1 << (t % 32);
      }
    });
    adjacent(data.geometry, cell.id).forEach(([id, side], d) => {
      neighbors[index * sides + d] = indices.get(id) ?? -1;
      neighborSides[index * sides + d] = side;
      if (cell.required[d] !== null && (graph || !records.has(id))) {
        boundary[index * sides + d] = remap.get(cell.required[d]);
      }
    });
  }
  return {geometry: data.geometry, words, wide, graph, sides, neighbors, neighborSides, width, height, active, boundary, domains, indices, records, tiles,
    edges: new ColorArray(tiles.flat().map(v => remap.get(v))), timeout, idleTimeout, mode, solver};
}

export function checkAssignments(prepared, assignments) {
  if (Object.keys(assignments).length !== prepared.records.size) throw Error('Soluzione incompleta.');
  for (const cell of prepared.records.values()) {
    const id = assignments[cell.id], tile = prepared.tiles[id];
    if (!Number.isInteger(id) || !tile ||
        (cell.fixed && tile.some((v, d) => v !== cell.fixed[d]))) {
      throw Error('Soluzione non valida o tessera fissata modificata.');
    }
    adjacent(prepared.geometry, cell.id).forEach(([id, side], d) => {
      const other = prepared.records.get(id);
      if ((cell.required[d] !== null && tile[d] !== cell.required[d]) ||
          (other && tile[d] !== prepared.tiles[assignments[other.id]]?.[side])) {
        throw Error('La soluzione contiene lati incompatibili.');
      }
    });
  }
  return assignments;
}
