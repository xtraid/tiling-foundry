#!/usr/bin/env python3
"""Build an independently consumable, fingerprinted browser solver package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/solver-web'
SOURCES = [
    'src/core/tile.c', 'src/core/region.c', 'src/solver/solver_serial.c',
    'src/solver/byte_support_table.c', 'src/solver/failed_leaf_trace.c',
    'src/solver/solver_event_trace.c', 'src/verify/verify_tiling.c',
    'packages/solver-web/bridge.c',
]
FLAGS = [
    '-std=c17', '-Wall', '-Wextra', '-Werror', '-O3', '-Iinclude', '--no-entry',
    '-sMODULARIZE=1', '-sEXPORT_ES6=1', '-sENVIRONMENT=worker,node',
    '-sASYNCIFY=1', '-sASYNCIFY_STACK_SIZE=65536',
    '-sALLOW_MEMORY_GROWTH=1', '-sMAXIMUM_MEMORY=268435456',
    '-sSTACK_SIZE=1048576', '-sFILESYSTEM=0',
    '-sEXPORTED_FUNCTIONS=["_foundry_enumerate","_malloc","_free"]',
    '-sEXPORTED_RUNTIME_METHODS=["ccall","HEAPU8","HEAPU32"]',
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emcc', default='emcc')
    parser.add_argument('--release', action='store_true', help='Require a clean checkout; use the release version.')
    args = parser.parse_args()
    compiler = subprocess.check_output([args.emcc, '--version'], text=True).splitlines()[0]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT))
    if args.release and dirty:
        parser.error('A release requires a clean committed checkout.')
    inputs = sorted(set(SOURCES + [
        str(p.relative_to(ROOT)) for pattern in ('include/**/*.h', 'src/solver/*.h', 'packages/solver-web/*')
        for p in ROOT.glob(pattern) if p.is_file()
    ] + ['tools/build_solver_web.py', 'LICENSE']))
    source_files = {name: sha256(ROOT / name) for name in inputs}
    source_hash = hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest()
    descriptor = json.loads((PACKAGE / 'package.json').read_text())
    version = descriptor['version'] if args.release else descriptor['version'] + '-dev.' + source_hash[:12]
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-dev\.[0-9a-f]+)?', version):
        parser.error('Invalid package version.')
    build_root = ROOT / 'build/solver-web'
    output = build_root / ('tiling-foundry-solver-web-' + version)
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.emcc, *FLAGS, *SOURCES, '-o', str(output / 'foundry.mjs')], cwd=ROOT, check=True)
    for name in ('client.mjs', 'worker.mjs', 'prepare.mjs', 'README.md'):
        shutil.copyfile(PACKAGE / name, output / name)
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    descriptor['version'] = version
    (output / 'package.json').write_text(json.dumps(descriptor, indent=2) + '\n')
    artifacts = ['foundry.mjs', 'foundry.wasm', 'client.mjs', 'worker.mjs', 'prepare.mjs',
                 'README.md', 'LICENSE', 'package.json']
    manifest = dict(
        name=descriptor['name'], version=version, api_version=1, solvers=['optimized', 'reference'],
        runtime='wasm', geometries=['square'],
        source=dict(repository='https://github.com/xtraid/tiling-foundry', revision=revision,
                    dirty=dirty, sha256=source_hash, files=source_files),
        build=dict(compiler=compiler, flags=FLAGS),
        limits=dict(max_tiles=32, max_used_colors=16, max_cells=4096, max_area=16384),
        files={name: dict(sha256=sha256(output / name), size=(output / name).stat().st_size) for name in artifacts},
    )
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = build_root / (output.name + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as tar:
        for name in artifacts + ['manifest.json']:
            tar.add(output / name, arcname='package/' + name)
    digest = sha256(archive)
    archive.with_name(archive.name + '.sha256').write_text(f'{digest}  {archive.name}\n')
    print(json.dumps(dict(package=str(output), archive=str(archive), sha256=digest, version=version), indent=2))


if __name__ == '__main__':
    main()
