"""Small synthetic fixture: published repository does not contain scraped recipe data."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from holizek.database import CatalogDB, duration_minutes, stable_id
from holizek.media import safe_source, synchronize_images


class CatalogTests(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(duration_minutes('100 perc (munka: 60 perc)'),100)
        self.assertIsNone(duration_minutes('Hozzávalók'))

    def test_missing_gallery_path_is_safe(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            self.assertIsNone(safe_source(p,'..\\secret.jpg'))
            self.assertIsNone(safe_source(p,'C:\\secret.jpg'))
            self.assertIsNone(safe_source(p,'a\\virus.exe'))
            self.assertEqual(safe_source(p,'haztartas_ma_export\\images\\test.jpg'),(p/'haztartas_ma_export'/'images'/'test.jpg').resolve())

    def test_database_model(self):
        with tempfile.TemporaryDirectory() as t:
            db=CatalogDB(t)
            self.assertEqual(db.count(),0)
            self.assertEqual(db.status_label,'SQLite')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM allergen_catalog').fetchone()[0],0)
            db.close()

    def test_source_import_and_duplicate_image_urls(self):
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        def cells(row, values):
            return '<row r="%d">%s</row>'%(row,''.join('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'%(col,row,val.replace('&','&amp;').replace('<','&lt;')) for col,val in values.items()))
        sheet1=[dict(zip('ABCDEFGHI',['cím','url','kategóriák','elkészítési_idő','hozzávalók','előkészítés','elkészítés','képek_url','képek_fájl'])),dict(zip('ABCDEFGHI',['Paprikás csirke','https://e.test/recipe/','Húsételek | Magyar','45 perc','csirke','felvág','főz','', '']))]
        sheet2=[dict(zip('ABCDE',['recept_cím','recept_url','sorszám','kép_url','helyi_fájl'])),
            dict(zip('ABCDE',['Paprikás csirke','https://e.test/recipe/','1','https://example.com/a.jpg','haztartas_ma_export\\images\\a.jpg'])),
            dict(zip('ABCDE',['Paprikás csirke','https://e.test/recipe/#comment','1','https://example.com/a.jpg','haztartas_ma_export\\images\\a.jpg']))]
        with tempfile.TemporaryDirectory() as t:
            t=Path(t)
            path=t/'input.xlsx'
            with ZipFile(path,'w') as z:
                for i,rows in [(1,sheet1),(2,sheet2)]:
                    content='<?xml version="1.0"?><worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>'%(ns,''.join(cells(j+1,row) for j,row in enumerate(rows)))
                    z.writestr(f'xl/worksheets/sheet{i}.xml',content)
            db=CatalogDB(t)
            a=db.import_workbook(path)
            self.assertEqual((a['recipes'],a['images'],a['skipped_rows']),(1,2,0))
            self.assertEqual(db.count('recipe_images'),1)
            self.assertEqual(db.count('image_source_rows'),2)
            self.assertEqual(len(db.categories()),2)
            original=t/'import'/'HOLiZEK'/'haztartas_ma_export'/'images'/'a.jpg'
            original.parent.mkdir(parents=True)
            original.write_bytes(b'fake-jpeg-fixture')
            b=synchronize_images(db)
            self.assertEqual(b['matched'],1)
            self.assertTrue((t/'data'/'HOLiZEK'/'images'/db.images(stable_id('https://e.test/recipe/'))[0][2]).is_file())
            db.import_workbook(path)
            self.assertEqual(db.count('recipes'),1)
            self.assertEqual(db.count('recipe_images'),1)
            self.assertEqual(db.count('image_source_rows'),4)
            db.close()


if __name__=='__main__': unittest.main()
