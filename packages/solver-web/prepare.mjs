/* Input validation and independent witness checking. No search implementation. */
export const limits = Object.freeze({
  max_tiles: 32, max_used_colors: 16, max_cells: 4096, max_area: 16384,
  max_palette: 128, default_timeout_seconds: 30,
});
const offsets = [[0, -1], [1, 0], [0, 1], [-1, 0]];

export function prepare(data) {
  if (!data || data.geometry !== 'square') throw Error('Il solver supporta per ora i quadrati.');
  const {palette, tiles, cells} = data;
  if (!Array.isArray(palette) || !palette.length || palette.length > limits.max_palette ||
      !palette.every(c => typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c))) {
    throw Error('Palette non valida.');
  }
  function edges(value, nullable = false) {
    if (!Array.isArray(value) || value.length !== 4 || !value.every(v =>
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
    if (!cell || typeof cell.id !== 'string' || !/^-?\d{1,7},-?\d{1,7}$/.test(cell.id)) {
      throw Error('Coordinate non valide.');
    }
    const [x, y] = cell.id.split(',').map(Number);
    const key = `${x},${y}`;
    if (Math.abs(x) > 1000000 || Math.abs(y) > 1000000 || records.has(key)) {
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
  const width = x1 - x0 + 1, height = y1 - y0 + 1, area = width * height;
  if (area > limits.max_area) throw Error('Il rettangolo della regione supera 16384 celle.');
  if (used.size > limits.max_used_colors) throw Error('Il solver supporta al massimo 16 colori usati.');
  // Colors are symbolic palette indices. Equal RGB values remain distinct.
  const remap = new Map([...used].sort((a, b) => a - b).map((v, i) => [v, i]));
  const active = new Uint8Array(area), boundary = new Uint8Array(area * 4).fill(255);
  const domains = new Uint32Array(area), indices = new Map();
  for (const cell of records.values()) {
    const index = (cell.y - y0) * width + cell.x - x0;
    indices.set(cell.id, index);
    active[index] = 1;
    tiles.forEach((tile, t) => {
      if ((!cell.fixed || tile.every((v, d) => v === cell.fixed[d])) &&
          cell.required.every((v, d) => v === null || tile[d] === v)) {
        domains[index] = (domains[index] | (1 << t)) >>> 0;
      }
    });
    offsets.forEach(([dx, dy], d) => {
      if (!records.has(`${cell.x + dx},${cell.y + dy}`) && cell.required[d] !== null) {
        boundary[index * 4 + d] = remap.get(cell.required[d]);
      }
    });
  }
  return {width, height, active, boundary, domains, indices, records, tiles,
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
    offsets.forEach(([dx, dy], d) => {
      const other = prepared.records.get(`${cell.x + dx},${cell.y + dy}`);
      if ((cell.required[d] !== null && tile[d] !== cell.required[d]) ||
          (other && tile[d] !== prepared.tiles[assignments[other.id]]?.[(d + 2) % 4])) {
        throw Error('La soluzione contiene lati incompatibili.');
      }
    });
  }
  return assignments;
}
