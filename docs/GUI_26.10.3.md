# HOLiZEK 26.10.3 – GUI standard megfelelés

## Megvalósítva

- Standard fejléc: állandó verzió, élő aktív adatbázis, magyar hosszú óra; sémaváltás nélküli adatbázis-kapcsolatállapot kiírás.
- `holinform_standards.design_runtime`: központi témabetöltés, ikon, élő témakövetés. Hiányzó Standards nem akadályozza az indítást.
- `holinform_standards.version_notice`: kizárólag a központi Updater helyi cache-éből ad verziójelzést.
- `holinform_standards.database_indicator.publish`: működő kapcsolathoz tartozó Updater-adatbázis-kijelzés.
- 1920×1000 munkafelület-korlát, per-felhasználó UI JSON, állapot és geometria megőrzése.
- Fejléc-határ dupla katt autooszlop-méretezés, monospaced Treeview központi témán keresztül, váltott sorok, függőleges/vízszintes görgetés.
- Tk nem blokkol az adatbázis csatlakoztatása és az import közben. Több eredmény üzenetsoron keresztül jut GUI-főszálra.
- Szabványos címsor és saját Tk/ttk dialógus natív `messagebox` helyett.

## Tesztelt

- Python unit tesztek és szintetikus SQL adatbázis;
- Tk/Xvfb képernyő- és interakcióteszt;
- 711 receptet tartalmazó, a korábban feltöltött munkafüzetből előállított SQLite másolat olvasása (értékek változtatása nélkül).

## Hátralevő kiadásellenőrzés

- Valós Windows 10/11 + központi sötét design ellenőrzése, többmonitoros negatív pozíció ellenőrzése.
- Standard validator futtatása az aktuális Standards repó ellen, a GitHub CI következő futásában.
- PostgreSQL éles szerverhez csatlakoztatás és Updaterből való indítás valós gépen.
- Projekt arculati ikon kijelölése a központi design editorban, amennyiben még nincs hozzárendelve.

A meglévő nyers Excel-forrás, SQLite állomány, partneradat, kép és forrástörténet változtatás nélkül marad.
