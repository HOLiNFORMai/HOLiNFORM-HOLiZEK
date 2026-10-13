## 26.10.4 – Windows regressziós teszt javítás

- A forrás biztonsági validálása változatlan, csak a tesztútvonal oldja fel a 8.3 temp-aliasokat.
- Folytatás: Windows/Linux GitHub Actions teszt és központi GUI-standard audit, célgép sötét témája.

## 26.10.3 – GUI standardizálás

- Commit után ellenőrizendő a `gui_standard.json` szerinti audit és a GitHub Actions.
- Updater 26.10.126 már tartalmazza a HOLiZEK forrásmodult; új HOLiZEK verzió az Updaterből frissíthető.
- Valós Windows céleszközön ellenőrizendő a sötét téma, táblázat fejléc/oszlop, hosszú sor, többmonitoros állapot és import után is működő képkapcsolatok.
- Következő fejlesztési irány: receptek szerkesztése, adagolás és allergiaadatok Partner-integrációjának biztonságos megtervezése.

# Következő fejlesztési lépések

1. A forrás ZIP Windows-asztali indítása a tényleges HOLiNFORM gyökér alatt; PostgreSQL DPAPI ellenőrzés.
2. A képek bemásolása és importja (19 429 bejegyzés, duplikált relatív fájlnevekkel).
3. Standards GUI validator, sötét téma és oszlopszűrés/automéretezés teljes megfeleltetése.
4. A mobil API terve a közös SQL séma fölé, jogosultságkezeléssel.
5. Szigorúan ellenőrzött allergénkatalógus a Partner személysémához, allergénmentességet nem feltételezve.
