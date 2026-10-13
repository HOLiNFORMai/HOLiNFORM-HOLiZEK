"""Import local recipe images using XLSX paths, preserving originals."""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path, PureWindowsPath

EXTENSIONS = {'.jpg','.jpeg','.png','.webp','.gif','.bmp'}


def safe_source(source_root: Path, raw_path: str):
    candidate = PureWindowsPath(raw_path)
    if candidate.is_absolute() or '..' in candidate.parts or candidate.drive:
        return None
    source_root = source_root.resolve()
    image = source_root.joinpath(*candidate.parts).resolve()
    if not image.is_relative_to(source_root) or image.suffix.lower() not in EXTENSIONS:
        return None
    return image


def synchronize_images(db, source_root: Path | None = None, progress=None):
    source_root = Path(source_root or db.paths['image_import'])
    target_root = db.paths['image_store']
    target_root.mkdir(parents=True, exist_ok=True)
    table = db.table('recipe_images')
    source_rows = db.execute(f'''SELECT recipe_id,image_key,source_relpath FROM {table}
        WHERE source_relpath <> '' AND (stored_relpath IS NULL OR import_state <> 'matched')''').fetchall()
    matched = missing = rejected = 0
    for idx, (recipe_id,image_key,relpath) in enumerate(source_rows,1):
        original = safe_source(source_root,relpath)
        if original is None:
            rejected += 1
            state = 'invalid-path'
            digest = stored_relpath = None
        elif not original.is_file():
            missing += 1
            state = 'missing'
            digest = stored_relpath = None
        else:
            digest = hashlib.sha256()
            with original.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024),b''):
                    digest.update(block)
            digest = digest.hexdigest()
            dest = target_root / digest[:2] / (digest+original.suffix.lower())
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.is_file():
                shutil.copy2(original,dest)
            stored_relpath = dest.relative_to(target_root).as_posix()
            state = 'matched'
            matched += 1
        db.execute(f'''UPDATE {table} SET stored_relpath=?,sha256=?,import_state=?
           WHERE recipe_id=? AND image_key=?''',(stored_relpath,digest,state,recipe_id,image_key))
        if progress and (idx%100==0 or idx==len(source_rows)):
            progress('Képek ellenőrzése',idx,len(source_rows))
        if idx%250==0:
            db.conn.commit()
    db.conn.commit()
    return {'total':len(source_rows),'matched':matched,'missing':missing,'invalid_path':rejected,
            'remaining':db.execute(f"SELECT COUNT(*) FROM {table} WHERE import_state <> 'matched'").fetchone()[0]}
