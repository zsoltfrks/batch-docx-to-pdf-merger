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

_RE_LEADING_NUMBER = re.compile(r'^(\d+)')
_RE_VERSIONED_PDF  = re.compile(r'^merged_v\d+\.pdf$')

INPUT_FOLDER        = r'C:\Temp\script test'
OUTPUT_FOLDER       = r'C:\Temp\script test\[output]'
INTERMEDIATE_FOLDER = os.path.join(OUTPUT_FOLDER, '_tmp')


def sort_by_leading_number(filename: str) -> int:
    """Return the leading integer in a filename, or infinity if there is none.

    Used as a sort key so that files like '2_intro.pdf' come before '10_end.pdf'
    (numeric order rather than lexicographic order).

    Args:
        filename: Bare filename, e.g. '3_chapter.pdf'.

    Returns:
        The integer found at the start of *filename*, or ``float('inf')`` so
        that files without a leading number sort to the end of the list.
    """
    match = _RE_LEADING_NUMBER.match(filename)
    return int(match.group(1)) if match else float('inf')


def between_first_last_underscore(s: str) -> str:
    """Return the substring between the first and last underscore, without a
    trailing '.pdf' suffix.

    Example: '0_foo_bar_1.pdf' → 'foo_bar'
    """
    first = s.find('_')
    last  = s.rfind('_')
    if first == -1 or last == -1 or first == last:
        return ''
    inner = s[first + 1:last].strip()
    if inner.lower().endswith('.pdf'):
        inner = inner[:-4].strip()
    return inner


def _copy_file(src: str, dst: str) -> None:
    """Copy *src* to *dst* as a raw binary copy.

    Used as a fallback throughout the pipeline to keep the file moving to the
    next stage even when an enhancement step (page-numbering, link insertion)
    cannot complete successfully.

    Args:
        src: Path to the source file.
        dst: Path to the destination file (created or overwritten).
    """
    with open(src, 'rb') as s, open(dst, 'wb') as d:
        d.write(s.read())


def _save_close_replace(doc, path: str) -> None:
    """Save a fitz document to *path* via a temp file.

    Closes *doc* before the final os.replace so Windows file locks are
    released before the rename.

    Args:
        doc: An open ``fitz.Document`` instance.  The document is closed by
            this function — callers must not use *doc* afterwards.
        path: The destination file path.  The file is first written to
            ``path + '.tmp'`` and then atomically renamed to *path*.

    Raises:
        Any exception raised by ``doc.save``, ``doc.close``, or
        ``os.replace`` is propagated to the caller.
    """
    temp = path + '.tmp'
    doc.save(temp)
    doc.close()
    os.replace(temp, path)


def safe_convert_single(docx_path: str, out_folder: str,
                        attempts: int = 2, delay: float = 0.5) -> bool:
    """Convert a single DOCX to PDF, suppressing Word COM noise.

    Calls ``docx2pdf.convert`` and redirects its stdout/stderr so that Word
    automation messages do not pollute the console.  On transient failures the
    call is retried with a short sleep between attempts.

    Args:
        docx_path: Absolute path to the source ``.docx`` file.
        out_folder: Directory where the converted PDF will be written.  The
            output filename is derived from *docx_path* by docx2pdf.
        attempts: Maximum number of conversion attempts before giving up.
        delay: Seconds to wait between retry attempts.

    Returns:
        ``True`` if the conversion succeeded, ``False`` if all attempts failed.
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
    """Draw a single TOC page onto a ReportLab canvas.

    Renders the heading at *top_y*, then one line per entry consisting of the
    chapter title, a dot-leader, and a right-aligned page label.

    Args:
        c: Active ``reportlab.pdfgen.canvas.Canvas`` instance.
        entries: List of ``(display_title, start_page, x, y)`` tuples for this
            page.  *x* and *y* are ReportLab coordinates (origin bottom-left).
        left_x: Left margin x-coordinate for text.
        right_x: Right margin x-coordinate; the page label is right-aligned here.
        top_y: y-coordinate where the heading is drawn.
        title: Heading string shown at the top of every TOC page.
        font_title_size: Point size for the heading font.
        font_line_size: Point size for the entry lines.
        dot_width: Width of a single dot character in *font_line_size* points,
            pre-computed by the caller so it is not recalculated per line.
    """
    c.setFont('Helvetica-Bold', font_title_size)
    c.drawString(left_x, top_y, title)
    c.setFont('Helvetica', font_line_size)
    for display_title, start_page, x, y in entries:
        title_width      = c.stringWidth(display_title, 'Helvetica', font_line_size)
        page_label       = f'{start_page + 1}. page'
        page_label_width = c.stringWidth(page_label, 'Helvetica', font_line_size)
        dots_count = max(
            int((right_x - left_x - title_width - page_label_width) / dot_width), 0
        )
        c.drawString(x, y, display_title)
        c.drawString(x + title_width, y, '.' * dots_count)
        c.drawString(right_x - page_label_width, y, page_label)


def create_toc_pdf(chapters, page_size=A4,
                   title: str = 'Table of Contents',
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
    left_x          = 60
    line_height     = 18
    title_gap       = 40
    font_title_size = 18
    font_line_size  = 11

    width, height = page_size
    right_x = width - 60
    top_y   = height - 100

    pages_entries = []
    cur_entries   = []
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
    tpl_right_x = tpl_w - 60
    tpl_top_y   = tpl_h - 100

    tmp_c = canvas.Canvas(BytesIO(), pagesize=(tpl_w, tpl_h))
    tmp_c.setFont('Helvetica', font_line_size)
    dot_width = tmp_c.stringWidth('.', 'Helvetica', font_line_size)

    writer = PdfWriter()
    for page_idx, entries in enumerate(pages_entries):
        tpl_page = tpl_pages[page_idx % len(tpl_pages)]
        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=(tpl_w, tpl_h))
        _draw_toc_page(c, entries, left_x, tpl_right_x, tpl_top_y,
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

    Some PDFs contain compressed streams with minor zlib errors that MuPDF
    cannot tolerate.  In those cases the file is re-written by pypdf (which is
    more lenient) and the result is validated with MuPDF before replacing the
    original.

    Args:
        path: Path to the PDF file to check and optionally repair.

    Returns:
        ``True`` if the file is already valid or was successfully repaired.
        ``False`` if the file cannot be opened and repair was not possible.
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
        with open(tmp, 'wb') as f:
            writer.write(f)
        try:
            fitz.open(tmp).close()
        except Exception as e2:
            os.remove(tmp)
            print(f"Warning: sanitized PDF still invalid for '{path}': {e2}")
            return False
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"Warning: failed to sanitize PDF '{path}': {e}")
        return False


def _insert_toc_links(doc, pages_entries, toc_page_count: int,
                      page_width: float, font_line_size: int) -> None:
    """Insert internal hyperlinks from TOC entries into an open fitz document.

    For each entry on each TOC page a clickable rectangle is added that jumps
    to the corresponding content page.  Failures on individual links are
    silently skipped so that a single bad entry does not abort the whole batch.

    Args:
        doc: Open ``fitz.Document`` that already contains both TOC and content
            pages.
        pages_entries: Per-TOC-page list of
            ``[(display_title, start_page, x, y), ...]`` as returned by
            ``create_toc_pdf``.  Coordinates are in ReportLab space
            (origin bottom-left).
        toc_page_count: Number of TOC pages at the start of *doc*; added to
            *start_page* to obtain the absolute destination page index.
        page_width: Width of the TOC pages in points.
        font_line_size: Font point size used for TOC entries; determines the
            height of each link rectangle.
    """
    right_x = page_width - 120
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
                page.insert_link({
                    'kind': fitz.LINK_GOTO,
                    'from': rect,
                    'page': int(dest_page),
                })


def _apply_toc_links(path: str, pages_entries, toc_page_count: int,
                     page_width: float, font_line_size: int) -> None:
    """Open *path*, insert TOC hyperlinks, and save the result in-place.

    Closes the fitz document and re-raises any exception, ensuring no file
    handles are leaked when the caller catches the error for a retry.

    Args:
        path: Path to the PDF to modify in-place.
        pages_entries: TOC entry list as returned by ``create_toc_pdf``.
        toc_page_count: Number of leading TOC pages in the document.
        page_width: Width of the TOC pages in points.
        font_line_size: Font size used for TOC entries.
    """
    doc = fitz.open(path)
    try:
        _insert_toc_links(doc, pages_entries, toc_page_count, page_width, font_line_size)
        _save_close_replace(doc, path)
    except Exception:
        with contextlib.suppress(Exception):
            doc.close()
        raise


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
    page_width = page_size[0]

    if not sanitize_pdf_if_needed(merged_pdf_path):
        print(f"Warning: skipping link insertion — '{merged_pdf_path}' could not be opened/repaired.")
        return

    try:
        _apply_toc_links(merged_pdf_path, pages_entries, toc_page_count, page_width, font_line_size)
    except Exception as e:
        print(f"Warning: fitz failed on '{merged_pdf_path}': {e}. Retrying after sanitize.")
        if not sanitize_pdf_if_needed(merged_pdf_path):
            print(f"Warning: sanitize failed; skipping link insertion for '{merged_pdf_path}'.")
            return
        try:
            _apply_toc_links(merged_pdf_path, pages_entries, toc_page_count, page_width, font_line_size)
        except Exception as e2:
            print(f"Warning: retry after sanitize also failed for '{merged_pdf_path}': {e2}")


def merge_pdfs_in_folder(folder_paths):
    """Merge PDFs from multiple folders, skipping script-generated files.

    Args:
        folder_paths: List of folder paths to scan.

    Returns:
        (PdfWriter, list): Writer containing all merged pages, and a list of
        (filename, start_page) chapter entries for TOC/bookmark creation.
    """
    generated_names  = {'merged.pdf', 'merged_with_toc.pdf', 'bookmarked.pdf'}
    intermediate_abs = os.path.abspath(INTERMEDIATE_FOLDER)
    pdf_candidates   = []
    seen             = set()

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

    writer       = PdfWriter()
    chapters     = []
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

    Numbers are rendered as "CURRENT / TOTAL page" at the bottom-right corner.

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
            text = f'{content_page_number} / {total_content_pages} page'
            page = doc[page_idx]
            r    = page.rect
            x0 = r.width  - textbox_width - margin
            y0 = r.height - textbox_height - margin - move_up_pixels
            x1 = r.width  - margin
            y1 = r.height - margin - move_up_pixels
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
    """Return the next available integer version for versioned PDFs in *folder_path*.

    Scans *folder_path* for files matching ``<base_name><N>.pdf``, collects all
    ``N`` values, and returns ``max(N) + 1``.  Returns ``1`` when no versioned
    files exist yet.

    Args:
        folder_path: Directory to scan for existing versioned PDFs.
        base_name: Filename prefix, e.g. ``'merged_v'``.

    Returns:
        The lowest integer that has not yet been used as a version suffix.
    """
    version_numbers = []
    for filename in os.listdir(folder_path):
        m = re.fullmatch(rf'{re.escape(base_name)}(\d+)\.pdf', filename)
        if m:
            version_numbers.append(int(m.group(1)))
    return max(version_numbers, default=0) + 1


def main() -> None:
    """Run the full batch DOCX-to-PDF merge pipeline.

    Steps performed in order:

    1. Convert every ``.docx`` in ``INPUT_FOLDER`` to PDF (skipping temp files
       and zero-byte files).
    2. Merge all PDFs from ``INPUT_FOLDER`` and ``OUTPUT_FOLDER`` into a single
       document, ordered by the leading number in each filename.
    3. Generate a Table of Contents (optionally overlaid on a template PDF).
    4. Prepend the TOC to the merged document and write it to
       ``INTERMEDIATE_FOLDER``.
    5. Insert clickable hyperlinks from each TOC entry to its target page.
    6. Add PDF outline bookmarks for each chapter.
    7. Stamp "CURRENT / TOTAL page" page numbers on every content page and
       write the result to ``OUTPUT_FOLDER`` as ``merged_v<N>.pdf``, where
       ``<N>`` is the next unused version number.
    """
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

    candidate_path    = os.path.join(OUTPUT_FOLDER, '!template.pdf')
    template_pdf_path = candidate_path if os.path.exists(candidate_path) else None

    merge_writer, chapters = merge_pdfs_in_folder([INPUT_FOLDER, OUTPUT_FOLDER])

    toc_buffer, pages_entries = create_toc_pdf(chapters, template_pdf_path=template_pdf_path)
    toc_pages = len(pages_entries)

    combined_writer = PdfWriter()
    for p in PdfReader(toc_buffer).pages:
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

    print(f"\nDone! Final PDF saved to:\n{final_pdf_path}\n")


if __name__ == '__main__':
    main()
