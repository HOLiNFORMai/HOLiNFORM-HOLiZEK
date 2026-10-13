"""Versioned SQL catalog with SQLite offline and PostgreSQL server adapters."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import re
import sqlite3
import uuid
from urllib.parse import urldefrag
from datetime import datetime, timezone
from pathlib import Path
from .workbook import read_rows
from .paths import module_paths


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def stable_id(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]


def file_sha256(file_path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(file_path, 'rb') as stream:
        for block in iter(lambda: stream.read(chunk_size), b''):
            digest.update(block)
    return digest.hexdigest()


def duration_minutes(value):
    # Extract a numeric duration only when the first token clearly states minutes.
    match = re.match(r'^\s*(\d{1,4})\s*(?:perc|perces|min)', value, re.I)
    return int(match.group(1)) if match else None


def _windows_pg_password() -> str:
    # Uses the existing Step-02 user-scoped DPAPI secret; never persists plaintext.
    if os.name != 'nt':
        raise RuntimeError('PostgreSQL-hoz HOLIZEK_PG_DSN vagy PGPASSWORD szükséges.')
    script = (
        "$ErrorActionPreference='Stop';"
        "$p=Join-Path $env:LOCALAPPDATA 'HOLiNFORM\\secrets\\postgresql_holinform_app.dpapi';"
        "$s=ConvertTo-SecureString ((Get-Content -LiteralPath $p -Raw).Trim());"
        "$b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);"
        "try {[Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($b))}"
        "finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b);$s.Dispose()}"
    )
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
        capture_output=True, timeout=12,check=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    secret = result.stdout.decode('utf-8-sig').strip() if result.returncode==0 else ''
    if not secret or len(secret)>256:
        raise RuntimeError('A PostgreSQL DPAPI felhasználói titok nem olvasható.')
    return secret


class CatalogDB:
    def __init__(self, root: Path, mode='local', dsn=None):
        self.root = Path(root)
        self.mode = mode
        self.server = mode == 'server'
        self.paths = module_paths(self.root)
        self.conn = None
        self.host = None
        if self.server:
            try:
                import psycopg
            except ImportError as e:
                raise RuntimeError('PostgreSQL módhoz telepíteni kell a psycopg csomagot.') from e
            # Password/DSN is only accepted through the environment, not logged or written.
            dsn = dsn or os.environ.get('HOLIZEK_PG_DSN')
            if dsn:
                self.conn = psycopg.connect(dsn, connect_timeout=10)
            else:
                cfg = self.root / 'config' / 'database' / 'postgresql.json'
                try:
                    settings = json.loads(cfg.read_text('utf-8'))
                except (OSError,ValueError) as e:
                    raise RuntimeError('Nincs PostgreSQL konfiguráció: ' + str(cfg)) from e
                password = os.environ.get('PGPASSWORD') or _windows_pg_password()
                try:
                    self.conn = psycopg.connect(
                        host=settings.get('host','127.0.0.1'),
                        port=int(settings.get('port',5432)),
                        dbname=settings.get('database',settings.get('dbname','holinform')),
                        user=settings.get('user','holinform_app'),password=password,connect_timeout=10)
                finally:
                    del password
            self.host = self.conn.info.host or 'Local'
        elif mode == 'local':
            self.paths['db'].parent.mkdir(parents=True, exist_ok=True)
            if not self.paths['db'].exists():
                packaged_seed = Path(__file__).resolve().parent.parent / 'seed' / 'holizek.sqlite3'
                if packaged_seed.is_file():
                    shutil.copyfile(packaged_seed, self.paths['db'])
            self.conn = sqlite3.connect(self.paths['db'], check_same_thread=False)
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('PRAGMA busy_timeout=10000')
        else:
            raise ValueError('Unsupported database mode: ' + mode)
        self.migrate()

    @property
    def status_label(self):
        if not self.conn:
            return 'Adatbázis: nincs kapcsolat'
        if not self.server:
            return 'SQLite'
        return 'PostgreSQL: Local' if self.host.lower() in ('127.0.0.1', '::1', 'localhost', 'local') else 'PostgreSQL: ' + self.host

    def table(self, name):
        return ('holizek.' if self.server else '') + name

    def sql(self, query):
        return query.replace('?', '%s') if self.server else query

    def execute(self, query, params=()):
        return self.conn.execute(self.sql(query), params)

    def executemany(self, query, params):
        return self.conn.executemany(self.sql(query), params)

    def migrate(self):
        migration = Path(__file__).resolve().parent.parent / 'sql' / ('001_postgresql.sql' if self.server else '001_sqlite.sql')
        if self.server:
            for clause in migration.read_text('utf-8').split(';'):
                if clause.strip():
                    self.conn.execute(clause)
        else:
            self.conn.executescript(migration.read_text('utf-8'))
        self.execute(f'INSERT INTO {self.table("schema_migrations")} (version,installed_utc) VALUES (?,?) ON CONFLICT (version) DO NOTHING', ('001', utc_now()))
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def count(self, table='recipes'):
        return self.execute(f'SELECT COUNT(*) FROM {self.table(table)}').fetchone()[0]

    def categories(self):
        return self.execute(f'SELECT category, COUNT(*) FROM {self.table("recipe_categories")} GROUP BY category ORDER BY category').fetchall()

    def search(self, term='', category='', limit=1000):
        pattern = '%' + term.strip().lower().replace('%', r'\%').replace('_', r'\_') + '%'
        args = []
        join = ''
        if category:
            join = f' JOIN {self.table("recipe_categories")} c ON c.recipe_id = r.recipe_id AND c.category = ?'
            args.append(category)
        args.extend([pattern,limit])
        return self.execute(f'''SELECT r.recipe_id,r.title,r.category_original,r.duration_minutes
           FROM {self.table("recipes")} r {join}
           WHERE LOWER(r.title) LIKE ? ESCAPE '\\' ORDER BY r.title LIMIT ?''', tuple(args)).fetchall()

    def recipe(self, recipe_id):
        c = self.execute(f'''SELECT title,source_url,category_original,duration_original,
          ingredients_original,preparation_original,instructions_original
          FROM {self.table("recipes")} WHERE recipe_id=?''', (recipe_id,))
        return c.fetchone()

    def images(self, recipe_id):
        return self.execute(f'''SELECT sequence_number, source_relpath,stored_relpath,remote_url,import_state
          FROM {self.table("recipe_images")} WHERE recipe_id=? ORDER BY sequence_number, image_key''', (recipe_id,)).fetchall()

    def import_workbook(self, workbook: Path, progress=None):
        workbook = Path(workbook)
        def report(message, done, total):
            if progress:
                progress(message, done, total)
        digest = file_sha256(workbook)
        run_id = str(uuid.uuid4())
        start = utc_now()
        report('Képadatok olvasása', 0, 1)
        recipes = list(read_rows(workbook,1))
        urls = {r.get('url','').strip(): r for r in recipes if r.get('url','').strip()}
        titles = {}
        for r in recipes:
            key = r.get('cím','').strip().casefold()
            if key:
                titles.setdefault(key,[]).append(r.get('url','').strip())
        image_rows = {}
        all_image_sources = []
        ignored = 0
        for number, row in enumerate(read_rows(workbook,2),2):
            source_url = row.get('recept_url','').strip()
            if source_url in urls:
                target, method = source_url, 'exact'
            elif urldefrag(source_url).url in urls:
                target, method = urldefrag(source_url).url, 'fragment_removed'
            else:
                options = titles.get(row.get('recept_cím','').strip().casefold(), [])
                target, method = (options[0], 'unique_title') if len(options)==1 else (None, 'unresolved')
            all_image_sources.append((number,row,target,method))
            if target:
                image_rows.setdefault(target,[]).append((row,method))
            else:
                ignored += 1
        recipes_count = 0
        images_count = 0
        seen = set()
        try:
            self.execute(f'''INSERT INTO {self.table("import_runs")}
                 (run_id,file_sha256,started_utc,state) VALUES (?,?,?,?)''', (run_id,digest,start,'working'))
            for number,image,target,method in all_image_sources:
                self.execute(f'''INSERT INTO {self.table("image_source_rows")}
                 (run_id,row_number,raw_json,resolved_recipe_id,match_method) VALUES (?,?,?,?,?)''',
                 (run_id,number,json.dumps(image,ensure_ascii=False),stable_id(target) if target else None,method))
            for row in recipes:
                url = row.get('url', '').strip()
                title = row.get('cím','').strip()
                if not url or not title:
                    ignored += 1
                    continue
                recipe_id = stable_id(url)
                seen.add(url)
                values = (recipe_id,url,title,row.get('kategóriák',''),row.get('elkészítési_idő',''),
                    duration_minutes(row.get('elkészítési_idő','')),row.get('hozzávalók',''),
                    row.get('előkészítés',''),row.get('elkészítés',''),row.get('képek_url',''),
                    row.get('képek_fájl',''),start)
                self.execute(f'''INSERT INTO {self.table("recipes")}
                  (recipe_id,source_url,title,category_original,duration_original,duration_minutes,
                   ingredients_original,preparation_original,instructions_original,image_urls_original,
                   image_files_original,last_import_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(recipe_id) DO UPDATE SET
                   title=excluded.title,category_original=excluded.category_original,
                   duration_original=excluded.duration_original,duration_minutes=excluded.duration_minutes,
                   ingredients_original=excluded.ingredients_original,preparation_original=excluded.preparation_original,
                   instructions_original=excluded.instructions_original,image_urls_original=excluded.image_urls_original,
                   image_files_original=excluded.image_files_original,last_import_utc=excluded.last_import_utc''', values)
                raw_json = json.dumps(row,ensure_ascii=False,sort_keys=True)
                self.execute(f'''INSERT INTO {self.table("recipe_source_history")}
                  (recipe_id,source_hash,raw_json,first_seen_utc) VALUES (?,?,?,?)
                  ON CONFLICT(recipe_id,source_hash) DO NOTHING''',
                  (recipe_id,hashlib.sha256(raw_json.encode('utf-8')).hexdigest(),raw_json,start))
                self.execute(f'DELETE FROM {self.table("recipe_categories")} WHERE recipe_id=?',(recipe_id,))
                categories = [s.strip() for s in row.get('kategóriák','').split('|') if s.strip()]
                for cat in dict.fromkeys(categories):
                    self.execute(f'''INSERT INTO {self.table("recipe_categories")}(recipe_id,category)
                      VALUES (?,?) ON CONFLICT DO NOTHING''',(recipe_id,cat))
                for image,match_method in image_rows.get(url, []):
                    try:
                        seq = int(image.get('sorszám',''))
                    except ValueError:
                        ignored += 1
                        continue
                    remote_url = image.get('kép_url', '').strip()
                    relpath = image.get('helyi_fájl','').strip()
                    source_url = image.get('recept_url','').strip()
                    image_key = stable_id(recipe_id+'|'+remote_url+'|'+relpath)
                    self.execute(f'''INSERT INTO {self.table("recipe_images")}
                     (recipe_id,image_key,sequence_number,source_url_original,match_method,remote_url,source_relpath)
                     VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(recipe_id,image_key) DO UPDATE SET
                     sequence_number=excluded.sequence_number,source_url_original=excluded.source_url_original,
                     match_method=excluded.match_method,remote_url=excluded.remote_url,source_relpath=excluded.source_relpath''',
                     (recipe_id,image_key,seq,source_url,match_method,remote_url,relpath))
                    images_count += 1
                recipes_count += 1
                if recipes_count % 50 == 0:
                    report('Receptek importálása', recipes_count, 711)
            # Original image sheet rows are preserved regardless of duplicate references.
            self.execute(f'''UPDATE {self.table("import_runs")} SET completed_utc=?,recipes_count=?,
                     images_count=?,state='success',message=? WHERE run_id=?''',
                     (utc_now(),recipes_count,images_count,f'Nem párosított/hibás sorok: {ignored}; forrás képsorok: {len(all_image_sources)}',run_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        report('Importálás kész', recipes_count, recipes_count or 1)
        return {'recipes':recipes_count,'images':images_count,'skipped_rows':ignored,'sha256':digest,'run_id':run_id}
