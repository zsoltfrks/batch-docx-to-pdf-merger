# Batch DOCX to PDF Merger

A Python pipeline that converts a folder of DOCX files to PDF, merges them in numeric order, prepends a clickable Table of Contents, adds PDF outline bookmarks, and stamps continuous page numbers, writing each run as a new versioned file so previous outputs are never overwritten.

---

## Features

- Converts all DOCX files in `INPUT_FOLDER` to individual PDFs via Word automation
- Merges PDFs in numeric order based on the leading number in each filename
- Generates a Table of Contents with dot-leaders, right-aligned page labels, and clickable hyperlinks to each section
- Optionally overlays the TOC onto a custom template PDF (`!template.pdf`)
- Inserts PDF outline bookmarks (sidebar navigation) for every chapter
- Stamps continuous "CURRENT / TOTAL oldal" page numbers on every content page, skipping TOC pages
- Automatically sanitizes and repairs PDFs with minor zlib/stream errors using a pypdf round-trip before MuPDF processes them
- Retries failed DOCX conversions with a configurable delay
- Versions output automatically (`merged_v1.pdf`, `merged_v2.pdf`, …) to prevent overwrites
- Skips Word temporary files (`~$…`), zero-byte files, and any PDF prefixed with `!`

---

## Requirements

- Python 3.7+
- Microsoft Word (required by `docx2pdf` for DOCX conversion on Windows/macOS)

**Python packages:**

```
docx2pdf
pypdf
reportlab
PyMuPDF
```

Install with:

```bash
pip install docx2pdf pypdf reportlab PyMuPDF
```

---

## Configuration

Open `main.py` and set the three path constants near the top:

```python
INPUT_FOLDER        = r'C:\Path\To\Your\DOCX_Folder'
OUTPUT_FOLDER       = r'C:\Path\To\Your\Output_Folder'
INTERMEDIATE_FOLDER = os.path.join(OUTPUT_FOLDER, '_tmp')
```

| Constant              | Purpose                                                                          |
| --------------------- | -------------------------------------------------------------------------------- |
| `INPUT_FOLDER`        | Directory containing your numbered `.docx` source files                          |
| `OUTPUT_FOLDER`       | Where converted PDFs and the final versioned output are written                  |
| `INTERMEDIATE_FOLDER` | Scratch directory (`_tmp`) for in-progress pipeline files; created automatically |

---

## Usage

1. Name your DOCX files with a leading number (see [File Naming](#file-naming)).
2. Set the three path constants in `main.py`.
3. Run the script:

```bash
python main.py
```

The pipeline executes these steps in order:

1. Converts every `.docx` in `INPUT_FOLDER` to PDF, writing results to `OUTPUT_FOLDER`
2. Collects and merges all PDFs from both folders in numeric filename order
3. Generates a Table of Contents (optionally rendered over a template PDF)
4. Prepends the TOC pages to the merged document
5. Inserts clickable hyperlinks from each TOC entry to its destination page
6. Adds PDF outline bookmarks for sidebar navigation
7. Stamps page numbers on all content pages
8. Writes the final file to `OUTPUT_FOLDER` as `merged_v<N>.pdf`

---

## File Naming

Files must be prefixed with a leading integer for correct merge order:

```
1_introduction.docx
2_methodology.docx
10_appendix.docx
```

Numeric sorting is used, so `2_…` comes before `10_…` (not lexicographic order). Files without a leading number are sorted to the end.

The TOC display title is derived from the text between the first and last underscore in the filename. Given `3_project_overview_final.pdf`, the TOC entry reads `project_overview`.

---

## Template PDF

If a file named `!template.pdf` exists in `OUTPUT_FOLDER`, the TOC text is overlaid onto that file's first page(s) instead of a blank white page. This lets you use a branded or pre-formatted cover sheet as the TOC background.

---

## Skipping Files During Merge

Prefix any PDF filename with `!` to exclude it from the merge. This is how the optional template file (`!template.pdf`) is kept out of the content pages. Script-generated filenames (`merged.pdf`, `merged_with_toc.pdf`, `bookmarked.pdf`, `merged_v*.pdf`) are also excluded automatically.

---

## Output

```
Output_Folder/
    1_introduction.pdf
    2_methodology.pdf
    …
    merged_v1.pdf       ← final output for first run
    merged_v2.pdf       ← second run, previous file untouched
    _tmp/
        merged_with_toc.pdf
        bookmarked.pdf
```

---

## Customization

**Page number format and position** — edit `add_page_numbers()` in `main.py`. The default renders `"CURRENT / TOTAL oldal"` right-aligned near the bottom of each content page. Adjust `margin`, `move_up_pixels`, `fontsize`, `textbox_width`, and `textbox_height` as needed.

**TOC title and language** — the `title` parameter of `create_toc_pdf()` defaults to `'Tartalomjegyzék'` (Hungarian for "Table of Contents"). Pass a different string to localize it.

**Conversion retries** — `safe_convert_single()` accepts `attempts` (default `2`) and `delay` (default `0.5` seconds). Increase these if Word automation on your machine is slow to initialize.

---

## Notes

- Close all DOCX files in Word before running the script; open files will be skipped or cause conversion errors.
- The `_tmp` folder contains intermediate pipeline files and can be deleted safely after each run.
- PDF sanitization is automatic: files with minor stream errors are repaired via a pypdf round-trip before MuPDF processes them. A warning is printed if a file cannot be repaired, and that step is skipped gracefully rather than aborting the run.

---

## License

Open-source and free to use for personal or commercial projects. No warranty is provided.
