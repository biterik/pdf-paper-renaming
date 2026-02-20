# Batch renaming of pdfs of scientific papers made easy
## Features

* Select multiple PDF files through a graphical user interface.
* Automatically fetches metadata (Year, First Author, Title) from the CrossRef API.
* Displays a preview of the proposed new filenames before making any changes.
* Allows to manually provide file names when the lookup failed.
* Renames the files in their original directory with a single click.

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
