# -----------------------------------------------------------------------------
# Copyright (c) 2025 Erik Bitzek
#
# Scientific PDF Renamer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later
# -----------------------------------------------------------------------------
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import os
import fitz  # PyMuPDF
import requests
import re
import threading
import difflib

# --- CONSTANTS ---

CROSSREF_API = "https://api.crossref.org/works"
CROSSREF_HEADERS = {'User-Agent': 'PDFRenamer/1.1 (mailto:ebitzek@example.com)'}

DOI_PATTERN = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')
DOI_WITH_PREFIX = re.compile(r'(?:doi[\s.:]{0,2})(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', re.IGNORECASE)

BOILERPLATE_PATTERNS = [
    re.compile(r'https?://\S+'),
    re.compile(r'www\.\S+'),
    re.compile(r'\S+@\S+\.\S+'),
    re.compile(r'Available\s+(online\s+)?at\s+\S+', re.IGNORECASE),
    re.compile(r'Downloaded\s+from\s+\S+', re.IGNORECASE),
    re.compile(r'Articles?\s+You\s+May\s+Be\s+Interested\s+In', re.IGNORECASE),
    re.compile(r'Contents?\s+lists?\s+available\s+at\s+\S+', re.IGNORECASE),
    re.compile(r'journal\s+homepage:\s*\S+', re.IGNORECASE),
    re.compile(r'ScienceDirect', re.IGNORECASE),
    re.compile(r'©\s*\d{4}.*?(?:Elsevier|Springer|Wiley|AIP|ACS|IOP|IEEE|Nature)\b.*', re.IGNORECASE),
    re.compile(r'All\s+rights?\s+reserved', re.IGNORECASE),
    re.compile(r'Published\s+by\s+\S+', re.IGNORECASE),
    re.compile(r'\bView\b\s*\n?\s*\bOnline\b', re.IGNORECASE),
    re.compile(r'\bExport\b\s*\n?\s*\bCitation\b', re.IGNORECASE),
]

TITLE_MATCH_THRESHOLD = 0.4

# --- TIER 1: DOI EXTRACTION ---

def extract_doi(text):
    """Extracts a DOI from text, preferring explicit doi: prefixed ones."""
    if not text:
        return None
    match = DOI_WITH_PREFIX.search(text)
    if match:
        doi = match.group(1)
    else:
        match = DOI_PATTERN.search(text)
        if match:
            doi = match.group(0)
        else:
            return None
    return doi.rstrip('.,;)')

def lookup_doi(doi):
    """Looks up metadata directly via CrossRef /works/{doi} endpoint."""
    try:
        url = f"{CROSSREF_API}/{requests.utils.quote(doi, safe='')}"
        response = requests.get(url, headers=CROSSREF_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok' and 'message' in data:
            return _parse_crossref_item(data['message'])
    except requests.exceptions.RequestException as e:
        print(f"DOI lookup failed for {doi}: {e}")
    except (KeyError, IndexError) as e:
        print(f"Could not parse DOI response for {doi}: {e}")
    return None

# --- TIER 2: FONT-SIZE TITLE EXTRACTION ---

def extract_title_by_font(page):
    """Extracts the paper title by finding the largest-font text on the page."""
    try:
        d = page.get_text("dict")
    except Exception:
        return None

    spans = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if len(text) < 3:
                    continue
                # Skip private-use Unicode (icon fonts)
                if any(ord(c) >= 0xE000 for c in text):
                    continue
                spans.append(span)

    if not spans:
        return None

    max_size = max(s["size"] for s in spans)

    # Collect spans at the largest font size (within 0.5pt tolerance)
    title_spans = [s for s in spans if abs(s["size"] - max_size) < 0.5]

    # Sort by vertical position then horizontal
    title_spans.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))

    title = " ".join(s["text"].strip() for s in title_spans)
    title = re.sub(r'\s+', ' ', title).strip()

    if len(title) < 10:
        return None

    return title

# --- TIER 3: CLEANED TEXT EXTRACTION ---

def extract_cleaned_text(page, max_chars=500):
    """Extracts text from a page with boilerplate and noise removed."""
    try:
        text = page.get_text("text")
    except Exception:
        return None

    # Remove private-use Unicode
    text = re.sub(r'[\ue000-\uf8ff]', '', text)

    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub('', text)

    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    return text[:max_chars] if text else None

# --- CROSSREF SEARCH AND VALIDATION ---

def search_crossref(text_query):
    """Searches CrossRef API and returns top results with scores."""
    if not text_query:
        return []
    try:
        params = {'query.bibliographic': text_query, 'rows': 3}
        response = requests.get(CROSSREF_API, params=params,
                                headers=CROSSREF_HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok' and data['message']['items']:
            results = []
            for item in data['message']['items']:
                parsed = _parse_crossref_item(item)
                if parsed:
                    parsed['score'] = item.get('score', 0)
                    results.append(parsed)
            return results
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
    except (KeyError, IndexError) as e:
        print(f"Could not parse API response: {e}")
    return []

def _parse_crossref_item(item):
    """Parses a single CrossRef API item into a metadata dict."""
    title = item.get('title', ['Untitled'])[0]
    # Strip MathML/XML tags from title
    title = re.sub(r'<[^>]+>', '', title)
    title = re.sub(r'\s+', ' ', title).strip()

    year = "UnknownYear"
    for date_field in ['published-print', 'published-online', 'published', 'issued', 'created']:
        if date_field in item and 'date-parts' in item[date_field]:
            parts = item[date_field]['date-parts']
            if parts and parts[0] and parts[0][0]:
                year = str(parts[0][0])
                break

    first_author = "UnknownAuthor"
    if 'author' in item and item['author']:
        for author in item['author']:
            if 'family' in author:
                first_author = author['family']
                break

    return {'year': year, 'author': first_author, 'title': title}

def validate_match(pdf_text, crossref_result):
    """Validates a CrossRef match against the PDF text. Returns a confidence string."""
    if not crossref_result or not pdf_text:
        return 'none'

    cr_title = crossref_result.get('title', '').lower()
    pdf_lower = pdf_text.lower()

    # Check how many significant words from the CrossRef title appear in the PDF
    title_words = [w for w in re.findall(r'[a-z]{4,}', cr_title)]
    if not title_words:
        return 'low'

    found = sum(1 for w in title_words if w in pdf_lower)
    word_ratio = found / len(title_words)

    # Also check sequence similarity
    seq_ratio = difflib.SequenceMatcher(None, cr_title[:200], pdf_lower[:500]).ratio()

    if word_ratio >= 0.5 or seq_ratio >= TITLE_MATCH_THRESHOLD:
        return 'high'
    elif word_ratio >= 0.25 or seq_ratio >= 0.25:
        return 'low'
    else:
        return 'none'

# --- MAIN IDENTIFICATION PIPELINE ---

def identify_paper(pdf_path):
    """Runs the three-tier identification pipeline on a PDF.
    Returns (metadata_dict, confidence_str, method_str) or (None, 'none', None).
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF {pdf_path}: {e}")
        return None, 'none', None

    num_pages = min(doc.page_count, 2)

    best_result = (None, 'none', None)

    for page_idx in range(num_pages):
        page = doc[page_idx]
        full_text = page.get_text("text")

        # Tier 1: DOI
        doi = extract_doi(full_text)
        if doi:
            metadata = lookup_doi(doi)
            if metadata:
                doc.close()
                return metadata, 'high', f'DOI (p{page_idx+1})'

        # Tier 2: Title by font size
        title = extract_title_by_font(page)
        if title:
            results = search_crossref(title)
            if results:
                top = results[0]
                confidence = validate_match(full_text, top)
                if confidence == 'high':
                    doc.close()
                    return top, 'high', f'Title (p{page_idx+1})'
                if confidence == 'low' and best_result[1] == 'none':
                    best_result = (top, 'low', f'Title (p{page_idx+1})')

        # Tier 3: Cleaned text
        cleaned = extract_cleaned_text(page)
        if cleaned:
            results = search_crossref(cleaned)
            if results:
                top = results[0]
                confidence = validate_match(full_text, top)
                if confidence == 'high':
                    doc.close()
                    return top, 'high', f'Text (p{page_idx+1})'
                if confidence == 'low' and best_result[1] == 'none':
                    best_result = (top, 'low', f'Text (p{page_idx+1})')

    doc.close()
    return best_result

def sanitize_filename(name):
    """Removes illegal characters from a string so it can be a valid filename."""
    base_name = name.replace('.pdf', '')
    sanitized = re.sub(r'[\\/*?:"<>|]', "", base_name)
    return sanitized[:150]

def format_new_filename(metadata):
    """Formats the new filename based on the extracted metadata."""
    if not metadata:
        return "COULD-NOT-PROCESS.pdf"
    year = metadata.get('year', 'UnknownYear')
    author = sanitize_filename(metadata.get('author', 'UnknownAuthor'))
    title = sanitize_filename(metadata.get('title', 'Untitled'))
    title = title.replace(' ', '-')
    return f"{year}-{author}-{title}.pdf"

# --- GUI APPLICATION CLASS ---

class PDFRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scientific PDF Renamer")
        self.root.geometry("900x600")
        
        self.file_list = []

        # Add the menu bar
        self.create_menu()

        # --- UI Setup ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.select_button = ttk.Button(top_frame, text="1. Select PDF Files", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=(0, 10))

        self.rename_button = ttk.Button(top_frame, text="2. Apply Renaming", command=self.rename_files, state=tk.DISABLED)
        self.rename_button.pack(side=tk.LEFT)
        
        self.tree = ttk.Treeview(main_frame, columns=("Original", "New", "Status"), show="headings")
        self.tree.heading("Original", text="Original Filename")
        self.tree.heading("New", text="Proposed New Filename")
        self.tree.heading("Status", text="Status")
        
        self.tree.column("Original", width=300)
        self.tree.column("New", width=400)
        self.tree.column("Status", width=150, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', self.on_double_click)

        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Select PDF files. Double-click a failed item to rename it manually.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding="2 5")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def create_menu(self):
        """Creates the main menu bar for the application."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # On macOS, the first menu is special. To make it look native,
        # we can add an "App" menu, but a simple "Help" menu is more
        # cross-platform friendly and avoids most issues.
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About Scientific PDF Renamer", command=self.show_about_dialog)

    def show_about_dialog(self):
        """Displays the 'About' information box."""
        messagebox.showinfo(
            "About Scientific PDF Renamer",
            "Scientific PDF Renamer v1.0\n\n"
            "Copyright (c) 2025 Erik Bitzek\n\n"
            "This program helps rename scientific papers using metadata from CrossRef. "
            "It is licensed under the GNU General Public License v3.0."
        )

    def select_files(self):
        """Opens a dialog to select PDF files and starts processing them."""
        filepaths = filedialog.askopenfilenames(
            title="Select scientific papers (PDFs)",
            filetypes=(("PDF Files", "*.pdf"), ("All files", "*.*"))
        )
        if not filepaths: return

        for i in self.tree.get_children(): self.tree.delete(i)
        self.file_list.clear()
        self.rename_button.config(state=tk.DISABLED)
        self.status_var.set("Processing... This may take a moment.")
        self.root.update_idletasks()

        thread = threading.Thread(target=self.process_files, args=(filepaths,), daemon=True)
        thread.start()

    def process_files(self, filepaths):
        """Processes each file to find metadata and suggests a new name."""
        for path in filepaths:
            original_dir = os.path.dirname(path)
            original_filename = os.path.basename(path)

            item_id = self.tree.insert("", "end", values=(original_filename, "", "Processing..."))
            self.root.update_idletasks()

            metadata, confidence, method = identify_paper(path)

            file_info = {
                'id': item_id,
                'original_path': path,
                'original_dir': original_dir,
                'new_path': None
            }

            if metadata and confidence == 'high':
                new_filename = format_new_filename(metadata)
                file_info['new_path'] = os.path.join(original_dir, new_filename)
                status = f"Ready [{method}]"
                self.tree.item(item_id, values=(original_filename, new_filename, status))
            elif metadata and confidence == 'low':
                new_filename = format_new_filename(metadata)
                file_info['new_path'] = os.path.join(original_dir, new_filename)
                status = f"Low Confidence [{method}]"
                self.tree.item(item_id, values=(original_filename, new_filename, status))
            else:
                status = "Error: Not Found"
                self.tree.item(item_id, values=(original_filename, "Double-click to enter name", status))

            self.file_list.append(file_info)

        if any(f['new_path'] for f in self.file_list):
            self.rename_button.config(state=tk.NORMAL)
            self.status_var.set("Review proposed names or double-click items to edit. Click 'Apply Renaming' when ready.")
        else:
            self.status_var.set("Processing complete. No files automatically matched. Double-click items to rename them manually.")

    def on_double_click(self, event):
        """Handles manual renaming when a user double-clicks a failed or low-confidence item."""
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        current_values = self.tree.item(item_id, 'values')
        if not current_values:
            return

        status = current_values[2]
        if status == "Error: Not Found" or "Low Confidence" in status:
            original_name = current_values[0]
            initial_value = ""
            if "Low Confidence" in status:
                initial_value = current_values[1].replace('.pdf', '')
            new_name = simpledialog.askstring(
                "Manual Rename",
                f"Enter the new filename for:\n{original_name}",
                initialvalue=initial_value,
                parent=self.root
            )

            if new_name and new_name.strip():
                final_name = sanitize_filename(new_name) + ".pdf"
                self.tree.item(item_id, values=(original_name, final_name, "Manual Entry"))
                for file_info in self.file_list:
                    if file_info['id'] == item_id:
                        file_info['new_path'] = os.path.join(file_info['original_dir'], final_name)
                        break
                self.rename_button.config(state=tk.NORMAL)
                self.status_var.set("Manual entry saved. Click 'Apply Renaming' when ready.")

    def rename_files(self):
        """Performs the actual file renaming based on the processed list."""
        if not messagebox.askyesno("Confirm Renaming", "Are you sure you want to rename these files?\nThis action cannot be undone."):
            return

        self.status_var.set("Renaming files...")
        success_count = 0
        fail_count = 0

        for file_info in self.file_list:
            if file_info['new_path']:
                try:
                    if os.path.exists(file_info['new_path']) and file_info['original_path'] != file_info['new_path']:
                        self.tree.item(file_info['id'], values=(self.tree.item(file_info['id'])['values'][0], self.tree.item(file_info['id'])['values'][1], "Error: Name exists"))
                        fail_count += 1
                        continue
                    
                    os.rename(file_info['original_path'], file_info['new_path'])
                    self.tree.item(file_info['id'], values=(self.tree.item(file_info['id'])['values'][0], self.tree.item(file_info['id'])['values'][1], "Renamed!"))
                    success_count += 1
                except OSError as e:
                    self.tree.item(file_info['id'], values=(self.tree.item(file_info['id'])['values'][0], self.tree.item(file_info['id'])['values'][1], "Error: OS Denied"))
                    print(f"Failed to rename {file_info['original_path']}: {e}")
                    fail_count += 1
        
        self.status_var.set(f"Renaming complete. Success: {success_count}, Failed: {fail_count}.")
        self.rename_button.config(state=tk.DISABLED)

# --- Main Execution ---
if __name__ == "__main__":
    try:
        import fitz
        import requests
    except ImportError:
        print("--------------------------------------------------")
        print("ERROR: Missing required libraries.")
        print("Please install them by running this command:")
        print("pip install PyMuPDF requests")
        print("--------------------------------------------------")
        exit()

    root = tk.Tk()
    app = PDFRenamerApp(root)
    root.mainloop()
