import tkinter as tk
from tkinter import filedialog, ttk, messagebox
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
        # Extract text from the first page, which usually contains the title and authors.
        # We limit it to the first 500 characters as that's plenty for a search query.
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
        # CrossRef API endpoint for searching works
        url = "https://api.crossref.org/works"
        # The 'query.bibliographic' parameter is good for searching with titles/authors
        params = {'query.bibliographic': text_query, 'rows': 1}
        # A user-agent is good practice for API calls
        headers = {'User-Agent': 'PDFRenamer/1.0 (mailto:user@example.com)'}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()
        
        if data['status'] == 'ok' and data['message']['items']:
            item = data['message']['items'][0]
            
            # --- Extract Title ---
            title = item.get('title', ['Untitled'])[0]
            
            # --- Extract Year ---
            year = "UnknownYear"
            if 'published' in item and 'date-parts' in item['published']:
                year = str(item['published']['date-parts'][0][0])
            elif 'created' in item and 'date-parts' in item['created']:
                 year = str(item['created']['date-parts'][0][0])

            # --- Extract First Author's Last Name ---
            first_author = "UnknownAuthor"
            if 'author' in item and item['author']:
                # The 'family' key usually holds the last name
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
    # Remove illegal characters for Windows/macOS/Linux filenames
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name)
    # Truncate to a reasonable length to avoid issues with path limits
    return sanitized[:150]

def format_new_filename(metadata):
    """Formats the new filename based on the extracted metadata."""
    if not metadata:
        return "COULD-NOT-PROCESS.pdf"
    
    year = metadata.get('year', 'UnknownYear')
    author = sanitize_filename(metadata.get('author', 'UnknownAuthor'))
    title = sanitize_filename(metadata.get('title', 'Untitled'))
    
    # Replace spaces with hyphens for readability
    title = title.replace(' ', '-')
    
    return f"{year}-{author}-{title}.pdf"


# --- GUI APPLICATION CLASS ---

class PDFRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scientific PDF Renamer")
        self.root.geometry("900x600")
        
        self.file_list = [] # This will store dicts with file info

        # --- UI Setup ---
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top frame for buttons
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        # Select Files Button
        self.select_button = ttk.Button(top_frame, text="1. Select PDF Files", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=(0, 10))

        # Rename Files Button
        self.rename_button = ttk.Button(top_frame, text="2. Apply Renaming", command=self.rename_files, state=tk.DISABLED)
        self.rename_button.pack(side=tk.LEFT)
        
        # Treeview for displaying file information
        self.tree = ttk.Treeview(main_frame, columns=("Original", "New", "Status"), show="headings")
        self.tree.heading("Original", text="Original Filename")
        self.tree.heading("New", text="Proposed New Filename")
        self.tree.heading("Status", text="Status")
        
        self.tree.column("Original", width=300)
        self.tree.column("New", width=400)
        self.tree.column("Status", width=150, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Please select your PDF files.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding="2 5")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def select_files(self):
        """Opens a dialog to select PDF files and starts processing them."""
        filepaths = filedialog.askopenfilenames(
            title="Select scientific papers (PDFs)",
            filetypes=(("PDF Files", "*.pdf"), ("All files", "*.*"))
        )
        
        if not filepaths:
            return

        # Clear previous results
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.file_list.clear()
        self.rename_button.config(state=tk.DISABLED)
        self.status_var.set("Processing... This may take a moment.")
        self.root.update_idletasks() # Force UI update

        # Use threading to prevent the GUI from freezing during processing
        thread = threading.Thread(target=self.process_files, args=(filepaths,), daemon=True)
        thread.start()

    def process_files(self, filepaths):
        """Processes each file to find metadata and suggests a new name."""
        for path in filepaths:
            original_dir = os.path.dirname(path)
            original_filename = os.path.basename(path)
            
            # Insert a placeholder row into the treeview
            item_id = self.tree.insert("", "end", values=(original_filename, "", "Processing..."))
            self.root.update_idletasks()

            # Extract text and search
            text = extract_text_from_pdf(path)
            metadata = search_crossref(text)

            if metadata:
                new_filename = format_new_filename(metadata)
                new_path = os.path.join(original_dir, new_filename)
                status = "Ready to Rename"
                self.tree.item(item_id, values=(original_filename, new_filename, status))
                
                # Store all necessary info for the renaming step
                self.file_list.append({
                    'id': item_id,
                    'original_path': path,
                    'new_path': new_path
                })
            else:
                status = "Error: Not Found"
                self.tree.item(item_id, values=(original_filename, "Could not find metadata.", status))
                self.file_list.append({
                    'id': item_id,
                    'original_path': path,
                    'new_path': None # No new path if we failed
                })
        
        # Enable the rename button if there are any files that can be renamed
        if any(f['new_path'] for f in self.file_list):
            self.rename_button.config(state=tk.NORMAL)
            self.status_var.set("Review the proposed names. Click 'Apply Renaming' when ready.")
        else:
            self.status_var.set("Processing complete. No files could be matched for renaming.")

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
                    # Check for potential name collisions before renaming
                    if os.path.exists(file_info['new_path']):
                         # Avoid overwriting a different file or itself if name is unchanged
                        if file_info['original_path'] != file_info['new_path']:
                            self.tree.item(file_info['id'], values=(self.tree.item(file_info['id'])['values'][0], self.tree.item(file_info['id'])['values'][1], "Error: Name exists"))
                            fail_count += 1
                            continue # Skip to the next file
                    
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
    # Before starting the app, check for dependencies
    try:
        import fitz
        import requests
    except ImportError:
        # A simple console message is better than a GUI popup here
        print("--------------------------------------------------")
        print("ERROR: Missing required libraries.")
        print("Please install them by running this command:")
        print("pip install PyMuPDF requests")
        print("--------------------------------------------------")
        exit()

    root = tk.Tk()
    app = PDFRenamerApp(root)
    root.mainloop()
