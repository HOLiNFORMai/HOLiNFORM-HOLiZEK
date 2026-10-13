# HOLiZEK — HOLiNFORM receptkezelő

**Első prototípus: 26.10.1.** Windows asztali receptkatalógus; a mobilkliens és a Partner-allergiák kezelésének adatmodellje előkészítve.

## Mit tud most?

- Receptkeresés, kategóriák és teljes receptszövegek megjelenítése, elkészítési idő, képgaléria.
- A forrás `Receptek` és `Képek` munkalapjának importja (XLSX, Microsoft Excel nélkül).
- Duplikált képhivatkozások összevonása; az összes eredeti forrássor megőrzése külön SQL-táblában.
- Képek párosítása pontos URL-lel, URL-fragmentum eltávolításával, vagy csak egyértelmű egyező receptcímmel.
- A képek importálása a forrásfájlok megtartásával, SHA-256 szerint tartós képtárba.
- Alapértelmezett SQLite önálló mód, választható PostgreSQL szerver mód, külön `holizek` sémában.
- A GUI a központi HOLiNFORM designt használja, ha az elérhető; különben natív témára áll vissza.

**Nem készült még el:** szerkesztő, automatikus bevásárlólista, készlet-alapú receptajánló, étkezéstervező, hitelesített allergén-elemzés, Partner-szinkron, mobilalkalmazás és natív Windows telepítő. Ezeket nem állítjuk működő funkciónak.

## Indítás

A forráskódból történő indításhoz Windows alatt Python 3.11+ szükséges. A gyökérútvonal `C:\HOLiNFORM` vagy a `C:\ProgramData\HOLiNFORM\global.json` szerinti útvonal. A felülethez a Tkinter szükséges (a hivatalos Windows Python része).

```powershell
py -3 main.py
```

A **csak a felhasználónak szánt, külön ZIP-átadás** tartalmazhat előre betöltött SQLite receptadatbázist a `seed/` mappában. A GitHub-repository szándékosan *nem* tárolja a felhasználó által feltöltött recepteket vagy képeket. A seed adatbázist első indításkor csak akkor másolja be a program, ha a céladatbázis még nem létezik; meglévő adatot soha nem ír felül.

## Recept-Excel importálása

A GUI `Excel importálása` gombja vagy:

```powershell
py -3 main.py --import-xlsx "D:\Adatok\haztartas_ma_receptek_eygedi.xlsx" --stats
```

A kiválasztott XLSX két munkalapja: `Receptek` és `Képek`. Az adatbetöltés ismételhető, nem törli a korábbi nyers rekordokat.

## Hová kerüljenek a képek?

Az Excelben szereplő relatív útvonalakat követve az **eredeti fájlnevekkel**:

```text
C:\HOLiNFORM\import\HOLiZEK\haztartas_ma_export\images\
```

A teljes `images` mappát másold ide. Ezután a GUI `Képek beolvasása` gombja vagy:

```powershell
py -3 main.py --sync-images
```

A program az ellenőrzött képeket SHA-256 azonosítóval a `<root>\data\HOLiZEK\images` tartós könyvtárba másolja. Nem törli az eredeti képeket; hibás vagy nem létező útvonalat jelez. A GUI-ban az eredeti képek megjelenítéséhez `Pillow` telepítése ajánlott: `py -3 -m pip install Pillow`.

## Központi PostgreSQL

```powershell
py -3 -m pip install "psycopg[binary]>=3.2,<4"
py -3 main.py --mode server --import-xlsx "D:\Adatok\receptek.xlsx"
py -3 main.py --mode server
```

A szerver mód soha nem kapcsol át hallgatólagosan SQLite-ra. A csatlakozás forrása: `HOLIZEK_PG_DSN` környezeti változó, vagy a központi `<root>\config\database\postgresql.json` **nem titkos** adatai és a HOLiNFORM Windows felhasználói DPAPI titoktára. A jelszó nem kerül a repo-ba, fájlba vagy naplóba. A `holizek` séma az adatokat elkülönítetten tárolja, a migráció `sql/001_postgresql.sql` alapján történik.

## Biztonság és allergének

A `person_allergies.partner_person_id` később a Partner személyazonosítójára hivatkozhat. A hiányzó allergénadat **nem** jelent allergénmentességet. V1-ben nincs orvosi biztonsági minősítés; a kezdeti adatmodell csak helyet készít a későbbi, igazolt adatoknak.

## Teszt

```powershell
py -3 -m unittest discover -s tests -v
```

## Projektállapot

Lásd: `docs/PROJECT_STATUS.md`, `docs/DECISIONS.md`, `docs/CURRENT_WORK.md`.
