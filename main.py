import contextlib
# new imports for DOCX conversion
import io as _io
import os
import re
import time
from io import BytesIO

import fitz
from docx2pdf import convert
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# FOLDER CONFIGURATION
PROJECT_ROOT = r'C:\Temp\script test'
INPUT_FOLDER = r'C:\Temp\script test'
OUTPUT_FOLDER = r'C:\Temp\script test\[output]'


# HELPER FUNCTIONS

def sort_by_leading_number(filename: str) -> int:
    """
    Sort helper based on the leading number at the beginning of the filename.

    Args:
        filename (str): The file name.

    Returns:
        int: The leading number, or infinity if no number is found.
    """
    match = re.match(r'(\d+)', filename)
    return int(match.group(1)) if match else float('inf')


def between_first_last_underscore(s: str) -> str:
    """
    Return the substring between the first and last underscore.

    Example:
        '0_IT üzemeltetés elérése_UJ.pdf' -> 'IT üzemeltetés elérése'

    Args:
        s (str): Input string.

    Returns:
        str: Text between the underscores, or empty string if not found.
    """
    first = s.find('_')
    last = s.rfind('_')
    if first == -1 or last == -1 or first == last:
        return ''
    # remove .pdf suffix and trim spaces
    inner = s[first + 1:last].strip()
    if inner.lower().endswith('.pdf'):
        inner = inner[:-4].strip()
    return inner


def create_toc_pdf(chapters, page_size=A4, title='Tartalomjegyzék', template_pdf_path: str = None):
    """
    Create the Table of Contents (TOC) PDF in memory.

    Args:
        chapters (list): List of (filename, start_page) tuples.
        page_size (tuple): Target page size (default: A4).
        title (str): TOC title text.
        template_pdf_path (str): Optional path of a template PDF to overlay TOC text onto.

    Returns:
        tuple:
            BytesIO: In‑memory PDF buffer containing the TOC.
            list: Per-page TOC entry list with coordinates for link creation.
    """
    width, height = page_size
    left_x = 60
    right_x = width - 60  # right-aligned text x coordinate
    top_y = height - 100  # TOC starts 40 pixels lower
    line_height = 18
    title_gap = 40
    font_title_size = 18
    font_line_size = 11

    # Layout entries across pages (ReportLab coordinates: origin bottom-left)
    pages_entries = []
    cur_entries = []
    y = top_y - title_gap
    for title_fname, start_page in chapters:
        cleaned = between_first_last_underscore(title_fname)
        display_title = cleaned if cleaned else title_fname.replace('.pdf', '')
        if y < 80:
            pages_entries.append(cur_entries)
            cur_entries = []
            y = top_y - title_gap
        cur_entries.append((display_title, start_page, left_x, y))
        y -= line_height
    if cur_entries:
        pages_entries.append(cur_entries)

    # If no template is provided, create simple TOC pages with ReportLab
    if not template_pdf_path or not os.path.exists(template_pdf_path):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        c.setFont('Helvetica-Bold', font_title_size)
        c.drawString(left_x, top_y, title)
        c.setFont('Helvetica', font_line_size)

        for page_idx, entries in enumerate(pages_entries):
            if page_idx != 0:
                c.showPage()
                c.setFont('Helvetica-Bold', font_title_size)
                c.drawString(left_x, top_y, title)
                c.setFont('Helvetica', font_line_size)
            for display_title, start_page, x, y in entries:
                # measure title and page number widths
                title_width = c.stringWidth(display_title, "Helvetica", font_line_size)
                page_number = f"{start_page + 1}. oldal"
                page_number_width = c.stringWidth(page_number, "Helvetica", font_line_size)

                # compute dot count to fill gap between left text and right text
                dots_width = right_x - left_x - title_width - page_number_width
                dots_count = max(int(dots_width / c.stringWidth('.', "Helvetica", font_line_size)), 0)
                dots = '.' * dots_count

                # draw title, dots and page number
                c.drawString(x, y, display_title)
                c.drawString(x + title_width, y, dots)
                c.drawString(right_x - page_number_width, y, page_number)
        c.save()
        buffer.seek(0)
        return buffer, pages_entries

    # If a template exists, overlay TOC text onto template pages
    tpl_reader = PdfReader(template_pdf_path)
    tpl_pages = tpl_reader.pages
    # determine template page size from first page
    tpl_w = float(tpl_pages[0].mediabox.width)
    tpl_h = float(tpl_pages[0].mediabox.height)
    left_x = 60
    right_x = tpl_w - 60  # right-aligned on template
    top_y = tpl_h - 100   # TOC starts 40 pixels lower on template pages

    writer = PdfWriter()
    for page_idx, entries in enumerate(pages_entries):
        # select template page (repeat if fewer template pages than TOC pages)
        tpl_page = tpl_pages[page_idx % len(tpl_pages)]
        # overlay text using ReportLab sized to template page
        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=(tpl_w, tpl_h))
        c.setFont('Helvetica-Bold', font_title_size)
        c.drawString(left_x, top_y, title)
        c.setFont('Helvetica', font_line_size)
        for display_title, start_page, x, y in entries:
            title_width = c.stringWidth(display_title, "Helvetica", font_line_size)
            page_number = f"{start_page + 1}. oldal"
            page_number_width = c.stringWidth(page_number, "Helvetica", font_line_size)

            dots_width = right_x - left_x - title_width - page_number_width
            dots_count = max(int(dots_width / c.stringWidth('.', "Helvetica", font_line_size)), 0)
            dots = '.' * dots_count

            c.drawString(x, y, display_title)
            c.drawString(x + title_width, y, dots)
            c.drawString(right_x - page_number_width, y, page_number)
        c.save()
        packet.seek(0)
        overlay_pdf = PdfReader(packet)
        # merge overlay page with a copy of the template page
        tpl_copy = tpl_page
        tpl_copy.merge_page(overlay_pdf.pages[0])
        writer.add_page(tpl_copy)

    out_buffer = BytesIO()
    writer.write(out_buffer)
    out_buffer.seek(0)
    return out_buffer, pages_entries


def sanitize_pdf_if_needed(path: str) -> bool:
    """
    Ensure that a PDF is openable by MuPDF; if not, attempt a pypdf round-trip repair.

    Args:
        path (str): Path to the PDF file.

    Returns:
        bool: True if the PDF is valid or successfully repaired, otherwise False.
    """
    try:
        doc = fitz.open(path)
        doc.close()
        return True
    except Exception as e:
        # common MuPDF zlib error (or other parse errors) — attempt a pypdf round-trip
        msg = str(e)
        if 'zlib' not in msg.lower() and 'stream' not in msg.lower():
            # not a candidate for this quick repair; surface the original error
            print(f"Warning: cannot open PDF '{path}': {e}")
            return False

        try:
            # read & re-write with pypdf to produce a fresh PDF file
            reader = PdfReader(path)
            writer = PdfWriter()
            for p in reader.pages:
                writer.add_page(p)
            tmp = path + '.sanitize.tmp'
            with open(tmp, 'wb') as out_f:
                writer.write(out_f)
            # final sanity check with fitz
            try:
                test = fitz.open(tmp)
                test.close()
            except Exception as e2:
                # sanitized file still bad
                os.remove(tmp)
                print(f"Warning: sanitized PDF still invalid for '{path}': {e2}")
                return False
            # replace original with sanitized version
            os.replace(tmp, path)
            return True
        except Exception as e3:
            print(f"Warning: failed to sanitize PDF '{path}': {e3}")
            return False


def add_links_to_merged_pdf(merged_pdf_path: str, pages_entries, toc_page_count: int, page_size=A4, font_line_size=11):
    """
    Add internal links from TOC entries to their target pages.

    Args:
        merged_pdf_path (str): Path to the combined PDF (TOC + content).
        pages_entries (list): TOC entries with coordinates per TOC page.
        toc_page_count (int): Number of TOC pages at the beginning of the document.
        page_size (tuple): Page size used when creating the TOC.
        font_line_size (int): Font size used for TOC entries (for link height).
    """
    # try to ensure the file is readable by fitz; attempt sanitize if needed
    if not sanitize_pdf_if_needed(merged_pdf_path):
        print(f"Warning: skipping adding links because '{merged_pdf_path}' could not be opened/ repaired.")
        return

    doc = None
    try:
        doc = fitz.open(merged_pdf_path)
        # Coordinates: ReportLab origin bottom-left; PyMuPDF origin top-left
        width, height = page_size
        right_x = width - 120

        for toc_page_idx, entries in enumerate(pages_entries):
            if toc_page_idx >= doc.page_count:
                # safety check
                continue
            page = doc[toc_page_idx]
            page_height = page.rect.height
            for display_title, start_page, x, y in entries:
                dest_page = start_page + toc_page_count  # destination in combined doc
                # Ensure dest_page exists
                if dest_page < 0 or dest_page >= doc.page_count:
                    continue
                # Convert ReportLab (bottom-left) y to PyMuPDF (top-left)
                y_top = page_height - y
                y_bottom = page_height - (y + font_line_size)
                rect = fitz.Rect(float(x), float(y_bottom), float(right_x), float(y_top))
                try:
                    page.insert_link({"kind": fitz.LINK_GOTO, "from": rect, "page": int(dest_page)})
                except Exception:
                    # insertion of a single link should not break the rest
                    continue
        # overwrite the file safely by saving to a temporary file then replacing original
        temp_path = merged_pdf_path + '.tmp'
        doc.save(temp_path)
        doc.close()
        os.replace(temp_path, merged_pdf_path)
    except Exception as e:
        # Try a sanitize+retry once
        if doc:
            try:
                doc.close()
            except Exception:
                pass
        print(f"Warning: fitz failed while adding links to '{merged_pdf_path}': {e}. Attempting sanitize and retry.")
        if sanitize_pdf_if_needed(merged_pdf_path):
            try:
                doc = fitz.open(merged_pdf_path)
                # retry the simple pass (best-effort)
                width, height = page_size
                right_x = width - 120
                for toc_page_idx, entries in enumerate(pages_entries):
                    if toc_page_idx >= doc.page_count:
                        continue
                    page = doc[toc_page_idx]
                    page_height = page.rect.height
                    for display_title, start_page, x, y in entries:
                        dest_page = start_page + toc_page_count
                        if 0 <= dest_page < doc.page_count:
                            y_top = page_height - y
                            y_bottom = page_height - (y + font_line_size)
                            rect = fitz.Rect(float(x), float(y_bottom), float(right_x), float(y_top))
                            try:
                                page.insert_link({"kind": fitz.LINK_GOTO, "from": rect, "page": int(dest_page)})
                            except Exception:
                                continue
                temp_path = merged_pdf_path + '.tmp'
                doc.save(temp_path)
                doc.close()
                os.replace(temp_path, merged_pdf_path)
            except Exception as e2:
                if doc:
                    try:
                        doc.close()
                    except Exception:
                        pass
                print(f"Warning: retry after sanitize also failed for '{merged_pdf_path}': {e2}")
        else:
            print(f"Warning: sanitize failed; skipping adding links to '{merged_pdf_path}'.")


def merge_pdfs_in_folder(folder_paths, output_pdf_path: str):
    """
    Merge PDF files from multiple folders (deduplicated), excluding
    script-generated temporary files and template files.

    Args:
        folder_paths (list): List of folder paths to scan for PDFs.
        output_pdf_path (str): Output path for the merged PDF.

    Returns:
        list: List of (filename, start_page) chapter entries in the merged document.
    """
    # normalize and exclude common generated names (lowercased)
    generated_names = {'merged.pdf', 'merged_with_toc.pdf', 'bookmarked.pdf'}
    pdf_candidates = []
    seen = set()

    for folder in folder_paths:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            full = os.path.join(folder, fname)
            if not os.path.isfile(full):
                continue
            lname = fname.lower()

            # skip non-pdfs, template/dedicated TOC marker files and temp files
            if not lname.endswith('.pdf'):
                continue
            if fname.startswith('!'):
                continue
            # skip any file that resides in the intermediate folder
            try:
                if os.path.commonpath([os.path.abspath(full), os.path.abspath(INTERMEDIATE_FOLDER)]) == os.path.abspath(INTERMEDIATE_FOLDER):
                    continue
            except Exception:
                pass

            # skip known generated filenames
            if lname in generated_names:
                continue
            # skip versioned final PDFs produced by this script (e.g. alapismeretek_v12.pdf)
            if re.match(r'^alapismeretek_v\d+\.pdf$', lname):
                continue

            # deduplicate by absolute path
            if os.path.abspath(full) in seen:
                continue
            seen.add(os.path.abspath(full))
            # store tuple for later sorting (use filename for sort key)
            pdf_candidates.append((fname, full))

    # sort by leading number in filename (keeps original behavior)
    pdf_candidates.sort(key=lambda it: sort_by_leading_number(it[0]))

    writer = PdfWriter()
    chapters = []
    current_page = 0  # 0-based page index for merged content

    for fname, fullpath in pdf_candidates:
        try:
            reader = PdfReader(fullpath)
        except Exception as e:
            print(f"Warning: failed to read PDF '{fullpath}', skipping: {e}")
            continue

        chapters.append((fname, current_page))

        for page in reader.pages:
            writer.add_page(page)

        current_page += len(reader.pages)

    # ensure output directory exists
    out_dir = os.path.dirname(output_pdf_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_pdf_path, 'wb') as merged:
        writer.write(merged)

    return chapters


def add_outline_bookmarks(input_pdf_path: str, output_pdf_path: str, chapters: list):
    """
    Add outline bookmarks to the PDF for each chapter.

    Args:
        input_pdf_path (str): Path to the input PDF.
        output_pdf_path (str): Path for the output PDF with bookmarks.
        chapters (list): List of (title, page_index) chapter entries.
    """
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    for title, page in chapters:
        display_title = title.replace('.pdf', '')
        writer.add_outline_item(display_title, page)

    with open(output_pdf_path, 'wb') as f:
        writer.write(f)


def add_page_numbers(input_pdf_path: str, output_pdf_path: str, toc_page_count: int = 0) -> None:
    """
    Add page numbers to the pages after the TOC.

    Args:
        input_pdf_path (str): Path to the input PDF.
        output_pdf_path (str): Path to the output PDF.
        toc_page_count (int): Number of initial TOC pages (these are not numbered).

    Notes:
        Page numbers are rendered in the format "CURRENT / TOTAL oldal"
        at the bottom-right corner of each content page.
    """
    # ensure PDF can be opened/sanitized first
    if not sanitize_pdf_if_needed(input_pdf_path):
        print(f"Warning: skipping page-numbering because '{input_pdf_path}' could not be opened/ repaired.")
        # copy input to output to keep pipeline moving
        try:
            with open(input_pdf_path, 'rb') as src, open(output_pdf_path, 'wb') as dst:
                dst.write(src.read())
        except Exception:
            pass
        return

    try:
        doc = fitz.open(input_pdf_path)
    except Exception as e:
        print(f"Warning: cannot open '{input_pdf_path}' for page-numbering: {e}")
        # copy input to output as fallback
        try:
            with open(input_pdf_path, 'rb') as src, open(output_pdf_path, 'wb') as dst:
                dst.write(src.read())
        except Exception:
            pass
        return

    total_pages = doc.page_count
    total_content_pages = max(total_pages - toc_page_count, 0)

    # Nothing to do if there are no content pages
    if total_content_pages <= 0:
        doc.close()
        try:
            os.replace(input_pdf_path, output_pdf_path)
        except Exception:
            with open(input_pdf_path, 'rb') as src, open(output_pdf_path, 'wb') as dst:
                dst.write(src.read())
        return

    margin = 20
    fontsize = 10
    textbox_width = 200
    textbox_height = 30

    # adjust this value to move the footer upward (pixels)
    # Example: 0 = current position, 10 = 10px upward, 40 = 40px upward
    move_up_pixels = 40

    for page_idx in range(doc.page_count):
        try:
            if page_idx >= toc_page_count:
                content_page_number = page_idx - toc_page_count + 1
                text = f"{content_page_number} / {total_content_pages} oldal"
                page = doc[page_idx]
                rect = page.rect

                x0 = rect.width - textbox_width - margin
                y0 = rect.height - textbox_height - margin
                x1 = rect.width - margin
                y1 = rect.height - margin

                # apply upward shift: subtract move_up_pixels from both y coordinates
                y0 = y0 - move_up_pixels
                y1 = y1 - move_up_pixels

                text_rect = fitz.Rect(x0, y0, x1, y1)

                page.insert_textbox(
                    text_rect,
                    text,
                    fontsize=fontsize,
                    fontname="helv",
                    align=2,
                    color=(0, 0, 0)
                )
        except Exception as e:
            print(f"Warning: Failed to write page number on page {page_idx + 1}: {e}")

    # save to temp and replace to avoid incremental-save issues
    temp_path = output_pdf_path + ".tmp"
    try:
        doc.save(temp_path)
        doc.close()
        os.replace(temp_path, output_pdf_path)
    except Exception as e:
        print(f"Warning: Could not save numbered PDF to '{output_pdf_path}': {e}")
        try:
            doc.close()
        except Exception:
            pass


def get_next_version_number(folder_path: str, base_name: str) -> int:
    """
    Determine the next version number for a PDF in the given folder.

    Args:
        folder_path (str): Folder to scan.
        base_name (str): Base filename prefix.

    Returns:
        int: The next available integer version number.
    """
    existing = [
        f for f in os.listdir(folder_path)
        if f.startswith(base_name) and f.endswith('.pdf')
    ]

    version_numbers = []
    for filename in existing:
        # match digits immediately after the provided base_name, e.g. 'alapismeretek_v1.pdf'
        m = re.search(rf'^{re.escape(base_name)}(\d+)\.pdf$', filename)
        if m:
            version_numbers.append(int(m.group(1)))

    return max(version_numbers, default=0) + 1


# -------------------------------------------------------------------
# MAIN WORKFLOW
# -------------------------------------------------------------------

# 1) DOCX → PDF conversion (file-by-file, to avoid Word temporary files)

# ensure output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# create a dedicated intermediate folder so generated files are not mixed with sources
INTERMEDIATE_FOLDER = os.path.join(OUTPUT_FOLDER, '_tmp')
os.makedirs(INTERMEDIATE_FOLDER, exist_ok=True)

# helper: convert a single docx quietly with a couple retries
def safe_convert_single(docx_path: str, out_folder: str, attempts: int = 2, delay: float = 0.5) -> bool:
    """
    Convert a single DOCX to PDF using docx2pdf.convert while suppressing stdout/stderr.

    Args:
        docx_path (str): Path to the source DOCX file.
        out_folder (str): Target folder for the produced PDF.
        attempts (int): Maximum number of conversion attempts.
        delay (float): Delay (seconds) between retries.

    Returns:
        bool: True on success, False on failure.
    """
    for attempt in range(1, attempts + 1):
        # redirect stdout/stderr so docx2pdf progress and Word COM messages don't clutter console
        fake_out = _io.StringIO()
        try:
            with contextlib.redirect_stdout(fake_out), contextlib.redirect_stderr(fake_out):
                convert(docx_path, out_folder)
            return True
        except Exception as e:
            # small backoff for transient COM issues
            if attempt < attempts:
                time.sleep(delay)
                continue
            # final attempt failed — emit concise warning only
            print(f"Warning: failed to convert '{docx_path}': {e}")
            return False

docx_list = sorted(
    [f for f in os.listdir(INPUT_FOLDER)
     if f.lower().endswith('.docx') and not f.startswith('~$')],
    key=sort_by_leading_number
)

for docx_file in docx_list:
    src_path = os.path.join(INPUT_FOLDER, docx_file)
    # skip obviously invalid files
    try:
        if os.path.getsize(src_path) == 0:
            print(f"Warning: skipping zero-byte file '{src_path}'")
            continue
    except OSError:
        print(f"Warning: cannot access '{src_path}', skipping")
        continue

    # use safe conversion (quiet + retries)
    safe_convert_single(src_path, OUTPUT_FOLDER)

# look for special TOC DOCX converted to PDF: filename starting with '!netoroldki'
template_pdf_path = None
candidate_name = '!netoroldki.pdf'
candidate_path = os.path.join(OUTPUT_FOLDER, candidate_name)
if os.path.exists(candidate_path):
    template_pdf_path = candidate_path

# 2) Merge PDFs
merged_pdf_path = os.path.join(INTERMEDIATE_FOLDER, 'merged.pdf')
chapters = merge_pdfs_in_folder([INPUT_FOLDER, OUTPUT_FOLDER], merged_pdf_path)

# 3) Create multi-page TOC (in memory) — without links
toc_buffer, pages_entries = create_toc_pdf(chapters, template_pdf_path=template_pdf_path)
toc_pages = len(pages_entries)

# 4) Prepend TOC pages to merged PDF
reader_main = PdfReader(merged_pdf_path)
reader_toc = PdfReader(toc_buffer)

combined_writer = PdfWriter()
for p in reader_toc.pages:
    combined_writer.add_page(p)
for page in reader_main.pages:
    combined_writer.add_page(page)

merged_with_toc_path = os.path.join(INTERMEDIATE_FOLDER, 'merged_with_toc.pdf')
with open(merged_with_toc_path, 'wb') as f:
    combined_writer.write(f)

# 5) Add internal links to TOC entries (now that content pages exist)
add_links_to_merged_pdf(merged_with_toc_path, pages_entries, toc_pages)

# 6) Add bookmarks / outline items (chapter targets shifted by TOC pages)
bookmarked_pdf_path = os.path.join(INTERMEDIATE_FOLDER, 'bookmarked.pdf')
chapters_with_offset = [(t, p + toc_pages) for (t, p) in chapters]
add_outline_bookmarks(merged_with_toc_path, bookmarked_pdf_path, chapters_with_offset)

# 7) Add page numbers and versioned output name
versioned_base_name = 'alapismeretek_v'
next_version = get_next_version_number(OUTPUT_FOLDER, versioned_base_name)

final_pdf_path = os.path.join(
    OUTPUT_FOLDER, f'{versioned_base_name}{next_version}.pdf'
)
# pass toc_pages so numbering starts after TOC and doesn't number TOC pages
add_page_numbers(bookmarked_pdf_path, final_pdf_path, toc_pages)

print(f"\nKÉSZ! A végső PDF itt van:\n{final_pdf_path}\n")

