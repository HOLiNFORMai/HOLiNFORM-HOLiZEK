"""Pure contract checks and optional real-Tk smoke test against synthetic rows."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from holizek.database import CatalogDB
from holizek.gui import ordered_items, safe_http_url


class GuiContractTests(unittest.TestCase):
    def test_sort_duration_keeps_missing_at_bottom_both_directions(self):
        rows = [('1', 'B', 'X', None), ('2', 'C', 'Y', 20),
                ('3', 'A', 'X', 10)]
        self.assertEqual([r[0] for r in ordered_items(rows, 'duration')],
                         ['3', '2', '1'])
        self.assertEqual([r[0] for r in ordered_items(rows, 'duration', True)],
                         ['2', '3', '1'])
        self.assertEqual([r[0] for r in ordered_items(rows, 'title')],
                         ['3', '1', '2'])

    def test_source_url_only_opens_http(self):
        self.assertEqual(safe_http_url(' https://example.com/r '),
                         'https://example.com/r')
        for text in ('', 'file:///etc/passwd', 'javascript:alert(1)',
                     'https://', 'data:text/html,x'):
            self.assertIsNone(safe_http_url(text))

    def test_ingredient_and_full_text_search(self):
        with tempfile.TemporaryDirectory() as folder:
            db = CatalogDB(folder)
            try:
                recipes = [
                    ('r1','https://example.test/1','Csirkepaprikás','Magyar',45,
                     'tejföl és csirke','daraboljuk','főzzük'),
                    ('r2','https://example.test/2','Zöldségfasírt','Vegetáriánus',30,
                     'lencse','áztatjuk','serpenyőben sütjük')]
                for rid, url, title, category, minutes, ingr, prep, method in recipes:
                    db.execute('''INSERT INTO recipes (recipe_id,source_url,title,category_original,
                      duration_original,duration_minutes,ingredients_original,preparation_original,
                      instructions_original,last_import_utc) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                      (rid,url,title,category,str(minutes)+' perc',minutes,ingr,prep,method,'2026-10-13T00:00:00Z'))
                    db.execute('INSERT INTO recipe_categories (recipe_id,category) VALUES (?,?)',(rid,category))
                db.conn.commit()
                self.assertEqual([r[0] for r in db.search('tejföl',scope='ingredients')],['r1'])
                self.assertEqual(db.search('tejföl',scope='title'),[])
                self.assertEqual([r[0] for r in db.search('serpenyő',scope='all')],['r2'])
                self.assertEqual([r[0] for r in db.search('csirke',category='Magyar',scope='all')],['r1'])
                with self.assertRaises(ValueError):
                    db.search('csirke',scope='r.title; DROP TABLE recipes')
            finally:
                db.close()


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'Requires visible Tk display')
class WindowSmokeTests(unittest.TestCase):
    def test_launch_select_filter_theme_fallback(self):
        from holizek.gui import Application
        with tempfile.TemporaryDirectory() as folder:
            win = Application(Path(folder))
            try:
                import time
                for _ in range(100):
                    win.update()
                    time.sleep(0.02)
                    if win.db is not None:
                        break
                self.assertIsNotNone(win.db)
                self.assertEqual(win.db_text.cget('text'), 'SQLite')
                self.assertEqual(win.table.heading('title', 'text'), 'Recept ▲')
                win.search_var.set('teszt')
                win.refresh()
                self.assertEqual(win.counter_label.cget('text'), '0 / 0 recept')
                win._save_geometry()
                self.assertTrue(win.paths['config'].is_file())
            finally:
                win._close()
