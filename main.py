import contextlib
from io import BytesIO, StringIO
import os
import re
import time

import fitz
from docx2pdf import convert
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

_RE_LEADING_NUMBER = re.compile(r'(\d+)')
_RE_VERSIONED_PDF = re.compile(r'^merged_v\d+\.pdf$')

PROJECT_ROOT       = r'C:\Temp\script test'
INPUT_FOLDER       = r'C:\Temp\script test'
OUTPUT_FOLDER      = r'C:\Temp\script test\[output]'
INTERMEDIATE_FOLDER = os.path.join(OUTPUT_FOLDER, '_tmp')


def sort_by_leading_number(filename: str) -> int:
    """Return the leading integer in a filename, or infinity if there is none."""
    match = _RE_LEADING_NUMBER.match(filename)
    return int(match.group(1)) if match else float('inf')


def between_first_last_underscore(s: str) -> str:
    """
    Return the substring between the first and last underscore, stripped of a
    trailing '.pdf' suffix.

    Example: '0_foo_bar_1.pdf' → 'foo_bar'
    """
    first = s.find('_')
    last = s.rfind('_')
    if first == -1 or last == -1 or first == last:
        return ''
    inner = s[first + 1:last].strip()
    if inner.lower().endswith('.pdf'):
        inner = inner[:-4].strip()
    return inner


def _copy_file(src: str, dst: str) -> None:
    with open(src, 'rb') as s, open(dst, 'wb') as d:
        d.write(s.read())


def _save_close_replace(doc, path: str) -> None:
    """Save a fitz document to *path* via a temp file.

    Closes *doc* before the final os.replace so Windows file locks are
    released before the rename.
    """
    temp = path + '.tmp'
    doc.save(temp)
    doc.close()
    os.replace(temp, path)


def safe_convert_single(docx_path: str, out_folder: str,
                        attempts: int = 2, delay: float = 0.5) -> bool:
    """Convert a single DOCX to PDF, suppressing Word COM noise.

    Returns True on success, False after all attempts have failed.
    """
    for attempt in range(1, attempts + 1):
        try:
            with contextlib.redirect_stdout(StringIO()), \
                 contextlib.redirect_stderr(StringIO()):
                convert(docx_path, out_folder)
            return True
        except Exception as e:
            if attempt < attempts:
                time.sleep(delay)
            else:
                print(f"Warning: failed to convert '{docx_path}': {e}")
    return False


def _draw_toc_page(c, entries, left_x: float, right_x: float,
                   top_y: float, title: str,
                   font_title_size: int, font_line_size: int,
                   dot_width: float) -> None:
    """Draw a single TOC page onto a ReportLab canvas."""
    c.setFont('Helvetica-Bold', font_title_size)
    c.drawString(left_x, top_y, title)
    c.setFont('Helvetica', font_line_size)
    for display_title, start_page, x, y in entries:
        title_width      = c.stringWidth(display_title, 'Helvetica', font_line_size)
        page_label       = f'{start_page + 1}. oldal'
        page_label_width = c.stringWidth(page_label, 'Helvetica', font_line_size)
        dots_count = max(
            int((right_x - left_x - title_width - page_label_width) / dot_width), 0
        )
        c.drawString(x, y, display_title)
        c.drawString(x + title_width, y, '.' * dots_count)
        c.drawString(right_x - page_label_width, y, page_label)


def create_toc_pdf(chapters, page_size=A4,
                   title: str = 'Tartalomjegyzék',
                   template_pdf_path: str = None):
    """Create the Table of Contents PDF in memory.

    Args:
        chapters: List of (filename, start_page) tuples.
        page_size: Target page size (default A4).
        title: Heading text shown on the TOC page(s).
        template_pdf_path: Optional path to a template PDF; when given,
            TOC text is overlaid onto that template instead of a blank page.

    Returns:
        (BytesIO, list): In-memory PDF buffer and per-page TOC entries
        with coordinates, used later for adding hyperlinks.
    """
    width, height = page_size
    left_x         = 60
    right_x        = width - 60
    top_y          = height - 100
    line_height    = 18
    title_gap      = 40
    font_title_size = 18
    font_line_size  = 11

    pages_entries: list = []
    cur_entries: list = []
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

    if not template_pdf_path or not os.path.exists(template_pdf_path):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        dot_width = c.stringWidth('.', 'Helvetica', font_line_size)
        for page_idx, entries in enumerate(pages_entries):
            if page_idx != 0:
                c.showPage()
            _draw_toc_page(c, entries, left_x, right_x, top_y,
                           title, font_title_size, font_line_size, dot_width)
        c.save()
        buffer.seek(0)
        return buffer, pages_entries

    tpl_reader = PdfReader(template_pdf_path)
    tpl_pages  = tpl_reader.pages
    tpl_w = float(tpl_pages[0].mediabox.width)
    tpl_h = float(tpl_pages[0].mediabox.height)
    left_x  = 60
    right_x = tpl_w - 60
    top_y   = tpl_h - 100

    _tmp_c = canvas.Canvas(BytesIO(), pagesize=(tpl_w, tpl_h))
    _tmp_c.setFont('Helvetica', font_line_size)
    dot_width = _tmp_c.stringWidth('.', 'Helvetica', font_line_size)

    writer = PdfWriter()
    for page_idx, entries in enumerate(pages_entries):
        tpl_page = tpl_pages[page_idx % len(tpl_pages)]
        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=(tpl_w, tpl_h))
        _draw_toc_page(c, entries, left_x, right_x, top_y,
                       title, font_title_size, font_line_size, dot_width)
        c.save()
        packet.seek(0)
        tpl_page.merge_page(PdfReader(packet).pages[0])
        writer.add_page(tpl_page)

    out_buffer = BytesIO()
    writer.write(out_buffer)
    out_buffer.seek(0)
    return out_buffer, pages_entries


def sanitize_pdf_if_needed(path: str) -> bool:
    """Ensure a PDF is readable by MuPDF, attempting a pypdf round-trip repair if not.

    Returns True if the file is valid or was successfully repaired, False otherwise.
    """
    try:
        fitz.open(path).close()
        return True
    except Exception as e:
        msg = str(e).lower()
        if 'zlib' not in msg and 'stream' not in msg:
            print(f"Warning: cannot open PDF '{path}': {e}")
            return False

    try:
        reader = PdfReader(path)
        writer = PdfWriter()
        for p in reader.pages:
            writer.add_page(p)
        tmp = path + '.sanitize.tmp'
        with open(tmp, 'wb') as out_f:
            writer.write(out_f)
        try:
            fitz.open(tmp).close()
        except Exception as e2:
            os.remove(tmp)
            print(f"Warning: sanitized PDF still invalid for '{path}': {e2}")
            return False
        os.replace(tmp, path)
        return True
    except Exception as e3:
        print(f"Warning: failed to sanitize PDF '{path}': {e3}")
        return False


def _insert_toc_links(doc, pages_entries, toc_page_count: int,
                      page_size, font_line_size: int) -> None:
    """Insert internal hyperlinks from TOC entries into an open fitz document."""
    width, _height = page_size
    right_x = width - 120
    for toc_page_idx, entries in enumerate(pages_entries):
        if toc_page_idx >= doc.page_count:
            continue
        page        = doc[toc_page_idx]
        page_height = page.rect.height
        for _title, start_page, x, y in entries:
            dest_page = start_page + toc_page_count
            if dest_page < 0 or dest_page >= doc.page_count:
                continue
            rect = fitz.Rect(
                float(x),
                page_height - (y + font_line_size),
                float(right_x),
                page_height - y,
            )
            with contextlib.suppress(Exception):
                page.insert_link({'kind': fitz.LINK_GOTO, 
                                  'from': rect,
                                  'page': int(dest_page)})


def add_links_to_merged_pdf(merged_pdf_path: str, pages_entries,
                             toc_page_count: int,
                             page_size=A4, font_line_size: int = 11) -> None:
    """Add clickable TOC links to an already-merged PDF.

    Args:
        merged_pdf_path: Path to the combined PDF (TOC + content pages).
        pages_entries: Per-page TOC entry list with coordinates.
        toc_page_count: Number of TOC pages prepended to the document.
        page_size: Page dimensions used when building the TOC.
        font_line_size: Font size used for TOC entries (determines link height).
    """
    if not sanitize_pdf_if_needed(merged_pdf_path):
        print(f"Warning: skipping link insertion — '{merged_pdf_path}' could not be opened/repaired.")
        return

    doc = None
    try:
        doc = fitz.open(merged_pdf_path)
        _insert_toc_links(doc, pages_entries, toc_page_count, page_size, font_line_size)
        _save_close_replace(doc, merged_pdf_path)
    except Exception as e:
        with contextlib.suppress(Exception):
            if doc:
                doc.close()
        print(f"Warning: fitz failed while adding links to '{merged_pdf_path}': {e}. Retrying after sanitize.")
        if sanitize_pdf_if_needed(merged_pdf_path):
            doc = None
            try:
                doc = fitz.open(merged_pdf_path)
                _insert_toc_links(doc, pages_entries, toc_page_count, page_size, font_line_size)
                _save_close_replace(doc, merged_pdf_path)
            except Exception as e2:
                with contextlib.suppress(Exception):
                    if doc:
                        doc.close()
                print(f"Warning: retry after sanitize also failed for '{merged_pdf_path}': {e2}")
        else:
            print(f"Warning: sanitize failed; skipping link insertion for '{merged_pdf_path}'.")


def merge_pdfs_in_folder(folder_paths):
    """Merge PDFs from multiple folders, skipping script-generated files.

    Args:
        folder_paths: List of folder paths to scan.

    Returns:
        (PdfWriter, list): Writer containing all merged pages, and a list of
        (filename, start_page) chapter entries for TOC/bookmark creation.
    """
    generated_names = {'merged.pdf', 'merged_with_toc.pdf', 'bookmarked.pdf'}
    intermediate_abs = os.path.abspath(INTERMEDIATE_FOLDER)
    pdf_candidates: list = []
    seen: set = set()

    for folder in folder_paths:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            full = os.path.join(folder, fname)
            if not os.path.isfile(full):
                continue
            lname = fname.lower()
            if not lname.endswith('.pdf'):
                continue
            if fname.startswith('!'):
                continue

            full_abs = os.path.abspath(full)

            with contextlib.suppress(Exception):
                if os.path.commonpath([full_abs, intermediate_abs]) == intermediate_abs:
                    continue

            if lname in generated_names or _RE_VERSIONED_PDF.match(lname):
                continue
            if full_abs in seen:
                continue

            seen.add(full_abs)
            pdf_candidates.append((fname, full))

    pdf_candidates.sort(key=lambda it: sort_by_leading_number(it[0]))

    writer = PdfWriter()
    chapters: list = []
    current_page = 0

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

    return writer, chapters


def add_outline_bookmarks(input_pdf_path: str, output_pdf_path: str,
                          chapters: list) -> None:
    """Write a PDF with an outline/bookmark entry for every chapter.

    Args:
        input_pdf_path: Source PDF path.
        output_pdf_path: Destination PDF path.
        chapters: List of (title, page_index) entries.
    """
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    writer.clone_reader_document_root(reader)
    for title, page in chapters:
        writer.add_outline_item(title.replace('.pdf', ''), page)
    with open(output_pdf_path, 'wb') as f:
        writer.write(f)


def add_page_numbers(input_pdf_path: str, output_pdf_path: str,
                     toc_page_count: int = 0) -> None:
    """Stamp page numbers onto every content page (pages after the TOC).

    Numbers are rendered as "CURRENT / TOTAL oldal" at the bottom-right corner.

    Args:
        input_pdf_path: Source PDF path.
        output_pdf_path: Destination PDF path.
        toc_page_count: Number of leading TOC pages that should not be numbered.
    """
    if not sanitize_pdf_if_needed(input_pdf_path):
        print(f"Warning: skipping page-numbering — '{input_pdf_path}' could not be opened/repaired.")
        _copy_file(input_pdf_path, output_pdf_path)
        return

    try:
        doc = fitz.open(input_pdf_path)
    except Exception as e:
        print(f"Warning: cannot open '{input_pdf_path}' for page-numbering: {e}")
        _copy_file(input_pdf_path, output_pdf_path)
        return

    total_content_pages = max(doc.page_count - toc_page_count, 0)
    if total_content_pages == 0:
        doc.close()
        try:
            os.replace(input_pdf_path, output_pdf_path)
        except Exception:
            _copy_file(input_pdf_path, output_pdf_path)
        return

    margin         = 20
    fontsize       = 10
    textbox_width  = 200
    textbox_height = 30
    move_up_pixels = 40

    for page_idx in range(toc_page_count, doc.page_count):
        try:
            content_page_number = page_idx - toc_page_count + 1
            text = f'{content_page_number} / {total_content_pages} oldal'
            page = doc[page_idx]
            r    = page.rect
            x0 = r.width  - textbox_width  - margin
            y0 = r.height - textbox_height - margin - move_up_pixels
            x1 = r.width  - margin
            y1 = r.height - margin         - move_up_pixels
            page.insert_textbox(
                fitz.Rect(x0, y0, x1, y1),
                text,
                fontsize=fontsize,
                fontname='helv',
                align=2,
                color=(0, 0, 0),
            )
        except Exception as e:
            print(f"Warning: failed to write page number on page {page_idx + 1}: {e}")

    try:
        _save_close_replace(doc, output_pdf_path)
    except Exception as e:
        print(f"Warning: could not save numbered PDF to '{output_pdf_path}': {e}")
        with contextlib.suppress(Exception):
            doc.close()


def get_next_version_number(folder_path: str, base_name: str) -> int:
    """Return the next integer version for files named <base_name><N>.pdf."""
    version_numbers = []
    for filename in os.listdir(folder_path):
        m = re.search(rf'^{re.escape(base_name)}(\d+)\.pdf$', filename)
        if m:
            version_numbers.append(int(m.group(1)))
    return max(version_numbers, default=0) + 1


def main() -> None:
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(INTERMEDIATE_FOLDER, exist_ok=True)

    docx_list = sorted(
        [f for f in os.listdir(INPUT_FOLDER)
         if f.lower().endswith('.docx') and not f.startswith('~$')],
        key=sort_by_leading_number,
    )
    for docx_file in docx_list:
        src_path = os.path.join(INPUT_FOLDER, docx_file)
        try:
            if os.path.getsize(src_path) == 0:
                print(f"Warning: skipping zero-byte file '{src_path}'")
                continue
        except OSError:
            print(f"Warning: cannot access '{src_path}', skipping")
            continue
        safe_convert_single(src_path, OUTPUT_FOLDER)

    template_pdf_path = None
    candidate_path = os.path.join(OUTPUT_FOLDER, '!netoroldki.pdf')
    if os.path.exists(candidate_path):
        template_pdf_path = candidate_path

    merge_writer, chapters = merge_pdfs_in_folder([INPUT_FOLDER, OUTPUT_FOLDER])

    toc_buffer, pages_entries = create_toc_pdf(chapters, template_pdf_path=template_pdf_path)
    toc_pages = len(pages_entries)

    reader_toc      = PdfReader(toc_buffer)
    combined_writer = PdfWriter()
    for p in reader_toc.pages:
        combined_writer.add_page(p)
    for page in merge_writer.pages:
        combined_writer.add_page(page)

    merged_with_toc_path = os.path.join(INTERMEDIATE_FOLDER, 'merged_with_toc.pdf')
    with open(merged_with_toc_path, 'wb') as f:
        combined_writer.write(f)

    add_links_to_merged_pdf(merged_with_toc_path, pages_entries, toc_pages)

    bookmarked_pdf_path  = os.path.join(INTERMEDIATE_FOLDER, 'bookmarked.pdf')
    chapters_with_offset = [(t, p + toc_pages) for t, p in chapters]
    add_outline_bookmarks(merged_with_toc_path, bookmarked_pdf_path, chapters_with_offset)

    versioned_base = 'merged_v'
    next_version   = get_next_version_number(OUTPUT_FOLDER, versioned_base)
    final_pdf_path = os.path.join(OUTPUT_FOLDER, f'{versioned_base}{next_version}.pdf')
    add_page_numbers(bookmarked_pdf_path, final_pdf_path, toc_pages)

    print(f"\nKÉSZ! A végső PDF itt van:\n{final_pdf_path}\n")


if __name__ == '__main__':
    main()
