/* Input validation and independent witness checking. No search implementation. */
export const limits = Object.freeze({
  max_tiles: 32, max_used_colors: 16, max_cells: 4096, max_area: 16384,
  max_palette: 128, default_timeout_seconds: 30,
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
  const graph = data.geometry !== 'square';
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
  if (!Array.isArray(tiles) || !tiles.length || tiles.length > limits.max_tiles) {
    throw Error('Il solver richiede da 1 a 32 tessere.');
  }
  tiles.forEach(t => edges(t));
  if (!Array.isArray(cells) || !cells.length || cells.length > limits.max_cells) {
    throw Error('La regione deve contenere da 1 a 4096 celle.');
  }
  const timeout = data.timeout_seconds ?? limits.default_timeout_seconds;
  if (typeof timeout !== 'number' || !Number.isFinite(timeout) || timeout < 1 || timeout > 120) {
    throw Error('Tempo limite non valido (1–120 secondi).');
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
  const width = x1 - x0 + 1, height = y1 - y0 + 1, area = graph ? cells.length : width * height;
  if (area > limits.max_area) throw Error('Il rettangolo della regione supera 16384 celle.');
  if (used.size > limits.max_used_colors) throw Error('Il solver supporta al massimo 16 colori usati.');
  // Colors are symbolic palette indices. Equal RGB values remain distinct.
  const remap = new Map([...used].sort((a, b) => a - b).map((v, i) => [v, i]));
  const active = new Uint8Array(area), boundary = new Uint8Array(area * sides).fill(255);
  const domains = new Uint32Array(area), indices = new Map();
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
        domains[index] = (domains[index] | (1 << t)) >>> 0;
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
  return {geometry: data.geometry, graph, sides, neighbors, neighborSides, width, height, active, boundary, domains, indices, records, tiles,
    edges: new Uint8Array(tiles.flat().map(v => remap.get(v))), timeout, mode, solver};
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
