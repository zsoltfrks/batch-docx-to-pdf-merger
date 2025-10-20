# Batch DOCX to Merged PDF with Page Numbers and Versioning

[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)]()
[![GitHub Repo Size](https://img.shields.io/github/repo-size/yourusername/yourrepo)]()
[![Last Commit](https://img.shields.io/github/last-commit/yourusername/yourrepo)]()

## Overview

This Python script automates the process of converting multiple DOCX files into PDFs, merging them into a single PDF, adding continuous page numbers, and managing versioning automatically. It is compatible with the latest `pypdf` (v3+) library.

---

## Features

* Converts all DOCX files in a specified folder to individual PDFs.
* Merges all PDFs in numeric order based on the leading number in the file names.
* Adds continuous page numbers to the merged PDF.
* Automatically tracks versions (`v1`, `v2`, `v3`, etc.) to prevent overwriting previous merged PDFs.
* Supports both single and multi-page DOCX files.

---

## Requirements

* Python 3.7+
* Libraries:

  * `docx2pdf`
  * `pypdf` (v3+)
  * `reportlab`

You can install the required libraries using pip:

```bash
pip install docx2pdf pypdf reportlab
```

---

## Usage

1. Set the folder paths for the DOCX input files and the output PDFs:

```python
inputFolder = r"C:\Path\To\Your\DOCX_Folder"
outputFolder = r"C:\Path\To\Your\Output_Folder"
```

2. Place all DOCX files you want to merge in the `inputFolder`.

3. Run the script.

4. The script will:

   * Convert DOCX files to PDFs.
   * Merge them in numeric order (based on leading numbers in file names).
   * Add continuous page numbers at the bottom of each page.
   * Save the merged PDF with versioning (`merged_numbered_v1.pdf`, `merged_numbered_v2.pdf`, etc.) in the `outputFolder`.

---

## File Naming Convention

To ensure proper numeric ordering, DOCX files should be named with a leading number, for example:

```
1_foo.docx
2_foo.docx
3_foo.docx
```

The script will sort and merge them in that order.

---

## Customization

* **Page Number Positioning**: You can modify the x and y coordinates in the script:

```python
can.drawString(float(page.mediabox.width)-60, 80, f"{i} / {total_pages} oldal")
```

* To center the page numbers:

```python
from reportlab.pdfbase.pdfmetrics import stringWidth
text = f"{i} / {total_pages} oldal"
page_width = float(page.mediabox.width)
text_width = stringWidth(text, "Helvetica", 10)
x_centered = (page_width - text_width)/2
can.drawString(x_centered, 80, text)
```

* Font type and size can also be adjusted with `can.setFont()`.

---

## Notes

* Ensure all DOCX files are closed before running the script.
* Large numbers of pages may take longer to process.
* The versioning feature prevents accidental overwrites of previous merged PDFs.

---

## License

This script is open-source and free to use for personal or commercial projects. No warranty is provided.
