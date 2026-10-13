# Projektállapot — 2026.10.13.

**V1: 26.10.1; repository kezdeti verzió.**

## Megvalósítva

- Receptkatalógus asztali Tk GUI kereséssel, kategóriákkal, részletekkel, képnézettel.
- XLSX-import (2 munkalap), teljes importnapló, nyers JSON snapshots és 19 429 képsor megőrzése.
- Újrafuttatható SQLite/PG adatbázismigrációs DDL, PostgreSQL külön séma.
- Képimport SHA-256 fizikai deduplikációval, forrásfájlok megtartásával.
- Allergén- és Partner-kapcsolathoz sémaszintű előkészítés.

## Ellenőrzött környezet

- Linux alatti Python unit teszt + a csatolt XLSX-szel tényleges SQLite import.
- A Windows GUI, a helyi felhasználó tényleges DPAPI/PostgreSQL csatlakozása, az Updater integráció és a natív Windows kiadás még nem volt élő Windows környezetben ellenőrizve.
- A központi Standards gépi GUI release-gate és manuális Windows vizuális validálása még hátra van; a V1 prototípus, **nem hivatalosan jóváhagyott telepítő**.

## Következő

- Windows GUI/Qt/Tk vizuális ellenőrzés, központi standard validator, éles PostgreSQL próba és installer.
- Receptmódosítás/hozzávaló-normalizálás ellenőrizhető módon; készlet, adag, menüterv.
- Partner kapcsolás csak személyazonosság és jogosultságkezelés jóváhagyásával.
