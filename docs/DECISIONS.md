# Döntések

- `26.10.1`: önálló, forrásmegőrző receptkatalógus SQLite-tal, és elkülönített PostgreSQL `holizek` SQL-sémával.
- Az Excel felhasználói tartalma nem kerül nyilvános Git-repositoryba.
- Képek: forrásrelatív utak `<root>/import/HOLiZEK/haztartas_ma_export/images`, tartós hash-alapú képtár `<root>/data/HOLiZEK/images`.
- A 19 429 eredeti képsor mind megmarad; ismétlődő képreferencia csak egyszer szerepel az aktív katalógusban.
- A Partner személyazonosító külső azonosító; az allergiaadatait csak igazoltan kezeljük, automatikus allergénmentes minősítés nincs.
- A Windows kliens elsősorban Python/Tk; a későbbi mobilkliens közös API-t és adatmodellt kap, nem közvetlenül nyitja meg a helyi SQLite fájlt.
- Központi design-runtime támogatás, natív GUI fallback, root/config standard és `YY.M.N` verzió.
