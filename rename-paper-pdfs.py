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

# --- METADATA AND RENAMING LOGIC ---

def extract_text_from_pdf(pdf_path):
    """Extracts text from the first page of a PDF to use for searching."""
    try:
        doc = fitz.open(pdf_path)
        text = doc[0].get_text("text")[:500]
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return None

def search_crossref(text_query):
    """Searches CrossRef API for metadata based on a text query."""
    if not text_query:
        return None
    try:
        url = "https://api.crossref.org/works"
        params = {'query.bibliographic': text_query, 'rows': 1}
        headers = {'User-Agent': 'PDFRenamer/1.0 (mailto:ebitzek@example.com)'}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok' and data['message']['items']:
            item = data['message']['items'][0]
            title = item.get('title', ['Untitled'])[0]
            year = "UnknownYear"
            if 'published' in item and 'date-parts' in item['published']:
                year = str(item['published']['date-parts'][0][0])
            elif 'created' in item and 'date-parts' in item['created']:
                 year = str(item['created']['date-parts'][0][0])
            first_author = "UnknownAuthor"
            if 'author' in item and item['author']:
                if 'family' in item['author'][0]:
                    first_author = item['author'][0]['family']
            return {'year': year, 'author': first_author, 'title': title}
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
    except (KeyError, IndexError) as e:
        print(f"Could not parse API response: {e}")
    return None

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

            text = extract_text_from_pdf(path)
            metadata = search_crossref(text)

            file_info = {
                'id': item_id,
                'original_path': path,
                'original_dir': original_dir,
                'new_path': None
            }

            if metadata:
                new_filename = format_new_filename(metadata)
                file_info['new_path'] = os.path.join(original_dir, new_filename)
                status = "Ready to Rename"
                self.tree.item(item_id, values=(original_filename, new_filename, status))
            else:
                status = "Error: Not Found"
                self.tree.item(item_id, values=(original_filename, "Double-click to enter name", status))
            
            self.file_list.append(file_info)
        
        if any(f['new_path'] for f in self.file_list):
            self.rename_button.config(state=tk.NORMAL)
            self.status_var.set("Review proposed names or double-click failed items to edit. Click 'Apply Renaming' when ready.")
        else:
            self.status_var.set("Processing complete. No files automatically matched. Double-click items to rename them manually.")

    def on_double_click(self, event):
        """Handles manual renaming when a user double-clicks a failed item."""
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        current_values = self.tree.item(item_id, 'values')
        if current_values and current_values[2] == "Error: Not Found":
            original_name = current_values[0]
            new_name = simpledialog.askstring(
                "Manual Rename",
                f"Enter the new filename for:\n{original_name}",
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
