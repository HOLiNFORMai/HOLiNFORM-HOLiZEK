PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, installed_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recipes (
  recipe_id TEXT PRIMARY KEY, source_url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
  category_original TEXT NOT NULL DEFAULT '', duration_original TEXT NOT NULL DEFAULT '',
  duration_minutes INTEGER, ingredients_original TEXT NOT NULL DEFAULT '',
  preparation_original TEXT NOT NULL DEFAULT '', instructions_original TEXT NOT NULL DEFAULT '',
  image_urls_original TEXT NOT NULL DEFAULT '', image_files_original TEXT NOT NULL DEFAULT '',
  last_import_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recipes_title ON recipes(title);
CREATE TABLE IF NOT EXISTS recipe_categories (
  recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), category TEXT NOT NULL,
  PRIMARY KEY(recipe_id, category)
);
CREATE INDEX IF NOT EXISTS idx_recipe_categories_category ON recipe_categories(category);
CREATE TABLE IF NOT EXISTS recipe_images (
  recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), image_key TEXT NOT NULL, sequence_number INTEGER NOT NULL,
  source_url_original TEXT NOT NULL DEFAULT '', match_method TEXT NOT NULL DEFAULT 'exact', remote_url TEXT NOT NULL, source_relpath TEXT NOT NULL DEFAULT '',
  stored_relpath TEXT, sha256 TEXT, import_state TEXT NOT NULL DEFAULT 'pending',
  PRIMARY KEY(recipe_id, image_key)
);
CREATE INDEX IF NOT EXISTS idx_images_import_state ON recipe_images(import_state);
CREATE TABLE IF NOT EXISTS recipe_source_history (
  recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), source_hash TEXT NOT NULL,
  raw_json TEXT NOT NULL, first_seen_utc TEXT NOT NULL,
  PRIMARY KEY(recipe_id, source_hash)
);
CREATE TABLE IF NOT EXISTS image_source_rows (
 run_id TEXT NOT NULL, row_number INTEGER NOT NULL, raw_json TEXT NOT NULL,
 resolved_recipe_id TEXT, match_method TEXT NOT NULL, PRIMARY KEY(run_id,row_number)
);
CREATE TABLE IF NOT EXISTS import_runs (
  run_id TEXT PRIMARY KEY, file_sha256 TEXT NOT NULL, started_utc TEXT NOT NULL,
  completed_utc TEXT, recipes_count INTEGER NOT NULL DEFAULT 0,
  images_count INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, message TEXT NOT NULL DEFAULT ''
);
-- Future Partner adapter: partner_person_id refers to a Partner identity, never a copied person row.
CREATE TABLE IF NOT EXISTS allergen_catalog (
  allergen_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, eu_code TEXT
);
CREATE TABLE IF NOT EXISTS person_allergies (
  partner_person_id TEXT NOT NULL, allergen_id TEXT NOT NULL REFERENCES allergen_catalog(allergen_id),
  declared_by TEXT, declared_utc TEXT, note TEXT,
  PRIMARY KEY(partner_person_id, allergen_id)
);
CREATE TABLE IF NOT EXISTS recipe_allergen_assessments (
  recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), allergen_id TEXT NOT NULL REFERENCES allergen_catalog(allergen_id),
  evidence TEXT NOT NULL, verification TEXT NOT NULL DEFAULT 'unverified',
  PRIMARY KEY(recipe_id, allergen_id)
);
