# OpenPDF

OpenPDF is a free local Windows PDF editor built with Python, Tkinter, PyMuPDF,
Pillow, and Tesseract OCR.

OpenPDF is under development. The current recommended app is the Python/Tkinter
desktop version. The cat logo is part of the OpenPDF brand.

## Current Features

- Open and save PDF files
- Print PDFs with `Ctrl+P`
- Add blank pages and insert pages from another PDF
- Delete, move, and reorder pages
- Replace an existing line of PDF text
- Insert editable text boxes
- Insert and scale images
- Draw lines, arrows, rectangles, squares, and circles
- Choose edge colour, fill colour, line style, and line width
- Move, resize, rotate, edit, and delete inserted objects
- Run OCR on opened PDF pages to add an invisible searchable text layer
- Use the OCR Generator tab to turn photos/screenshots into searchable PDFs
- Undo recent editing operations with `Ctrl+Z`

## Portable App

The rebuilt portable app is in:

```text
dist\OpenPDF\OpenPDF.exe
```

To share it on a USB stick, copy the whole `dist\OpenPDF` folder. Do not copy
only `OpenPDF.exe`; it needs the `_internal` and `tesseract` folders beside it.

The portable ZIP is:

```text
dist\OpenPDF_Portable.zip
```

## Run From Source

1. Install Python 3.14 or newer.
2. Run `Setup.bat`.
3. Install Tesseract OCR if setup reports that it is missing:
   `https://github.com/UB-Mannheim/tesseract/wiki`
4. Run `Start Open PDF.bat`.

## Build Portable EXE

Run:

```powershell
.\build_portable.ps1
```

This creates:

```text
dist\OpenPDF\OpenPDF.exe
dist\OpenPDF_Portable.zip
```

## OCR Notes

OCR on an opened PDF adds an invisible searchable text layer. The page may look
unchanged. After OCR finishes, save the PDF and test by searching/selecting text
in a PDF reader.

If OCR reports zero readable words, the scan may already contain real text, may
be too blurry, or may need better contrast/language support.

## Print Notes

Press `Ctrl+P` or use `File > Print`. OpenPDF sends a temporary PDF to Windows
print through the default PDF reader. A PDF reader and printer must be installed
for printing to work.
