# Markdown to DOCX Converter

This tool converts use-case Markdown specifications into native Word `.docx` files through an interactive console menu.

## Requirements

Install Python 3.10 or later and the required package:

```powershell
python -m pip install python-docx
```

## Run the console

Run this command from the `Tashen-Document` root directory:

```powershell
python tools/markdown_to_docx.py --console
```

Running the script without arguments opens the same console menu.

## Console example

```text
PS C:\Tashen-Document> python tools/markdown_to_docx.py --console

=== Use-case Markdown to DOCX ===
1. Convert one Markdown file
2. Convert all Markdown files in a folder
Choose an option [2]: 2
Select the Markdown folder in the folder picker.
[Windows folder picker opens]
Selected folder: C:\Tashen-Document\use-case
Output folder [use-case-docx]: use-case-docx

Created: use-case-docx\access-control\permissions\create-permission.docx
Created: use-case-docx\access-control\permissions\delete-permission.docx
Created: use-case-docx\auth\login.docx
Created: use-case-docx\catalog\books\create-book.docx
...
Completed: 124 file(s)
```

When option `2` is selected, the tool recursively scans the selected folder for `.md` files, skips `README.md`, converts every specification to `.docx`, and preserves the source folder structure in the output folder.

Use a separate output folder to avoid overwriting the Markdown specifications.
