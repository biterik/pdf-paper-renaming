# Batch renaming of pdfs of scientific papers made easy
## Features

* Select multiple PDF files through a graphical user interface.
* Automatically fetches metadata (Year, First Author, Title, Journal) from the CrossRef API.
* Customizable filename patterns using placeholders: `{Year}`, `{Author}`, `{Title}`, `{Journal}`, `{Tags}`.
* Built-in journal abbreviation database (~30,000 journals) for short journal names in filenames.
* User-defined tags (e.g., "glass, fracture") that can be included in filenames.
* Displays a live preview of the proposed new filenames before making any changes.
* Allows to manually provide file names when the lookup failed.
* Renames the files in their original directory with a single click.
* Settings (selected pattern and tags) are persisted across sessions.

## Filename Patterns

Choose from preset patterns or define your own using the following placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{Year}` | Publication year | 2024 |
| `{Author}` | First author's last name | Zhang |
| `{Title}` | Paper title | Room-temperature-plasticity-in-amorphous-SiO2 |
| `{Journal}` | Abbreviated journal name | Acta-Mater. |
| `{Tags}` | User-defined tags | glass-fracture |

### Preset patterns

* `{Year}-{Author}-{Title}` (default)
* `{Author}-{Year}-{Title}`
* `{Year}-{Author}-{Journal}-{Title}`
* `{Year}-{Author}-{Tags}-{Title}`
* `{Year}-{Author}-{Journal}-{Tags}-{Title}`

You can also enter a custom pattern via the "Custom..." option in the dropdown.

### Tags

Tags are free-text labels that you type in the Tags field, separated by commas. They are joined with hyphens in the filename. For example, entering `glass, fracture` produces `glass-fracture` in the filename. Tags apply to all files in the current batch and are saved between sessions.

## Installation
You can also directly install the binaries provided in the section on the downloads.

1.  Clone this repository.
2.  Ensure you have Miniconda or Anaconda installed.
3.  Open your terminal or Anaconda Prompt, navigate to the project directory, and run the following command to create the environment:

    ```bash
    conda env create -f environment.yml
    ```

4.  Activate the new environment:

    ```bash
    conda activate pdf-renamer-env
    ```


## Download

You can download the latest version of the application for Windows, macOS, and Linux from the
[**GitHub Releases page**](https://github.com/biterik/pdf-paper-renaming/releases/).

### macOS: First Launch

Since the application is not code-signed, macOS will block it on first launch. To open it:

1. Double-click the app. A dialog will say it "can't be opened."
2. Open **System Settings > Privacy & Security**.
3. Scroll down to find a message about "PaperPDFRenamer" being blocked.
4. Click **Open Anyway** and confirm.
