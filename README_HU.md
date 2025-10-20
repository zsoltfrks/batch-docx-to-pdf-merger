## Használat

1. Telepítsd a szükséges Python csomagokat:

```bash
pip install docx2pdf pypdf reportlab
```

2. Állítsd be a script tetején az elérési útvonalakat:

```python
inputFolder = r"C:\script test"
outputFolder = r"C:\script test\[output]"
```

3. Futtasd a scriptet:

```bash
python mergedocx.py
```

A script lefutás után a `[output]` mappában megjelenik egy új PDF:

```
merged_numbered_v1.pdf
```

Ha újból lefuttatod, automatikusan `merged_numbered_v2.pdf`, majd `v3`, stb.

---

## Fő funkciók

| Funkció       | Leírás                                                               |
| ------------- | -------------------------------------------------------------------- |
| DOCX → PDF    | Automatikus konvertálás az eredeti fájlnév megtartásával             |
| PDF mergelés  | Számsorrend alapján (pl. 01, 02, 03...)                              |
| Oldalszámozás | „X / Y oldal” formátumban, automatikusan                             |
| Verziókövetés | Nem írja felül a meglévő PDF-eket, hanem `v1`, `v2`, `v3` néven ment |
