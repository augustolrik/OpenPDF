# PDFeditEasy

PDFeditEasy is a local Windows PDF editor built with Python, Tkinter, PyMuPDF,
Pillow, and Tesseract OCR.

## Features

- OCR Generator tab for turning photos or screenshots into searchable PDFs
- Open and save PDF files
- Replace an existing line of PDF text
- Insert bordered text boxes
- Draw solid, dotted, and arrow lines
- Draw rectangles, squares, and circles
- Choose separate edge and fill colours
- Select inserted objects and drag them to move
- Resize objects with corner handles
- Rotate or delete selected photos, text, lines, and figures
- Insert and scale images
- Add blank pages
- Insert pages from another PDF
- Delete and reorder pages
- Run OCR on specific pages and add invisible searchable text
- Undo the last 15 editing operations

## Install and start

1. Run `Setup.bat`.
2. Install Tesseract OCR if Setup reports that it is missing:
   https://github.com/UB-Mannheim/tesseract/wiki
3. Run `Start PDFeditEasy.bat`.

## Modern HTML GUI Prototype

A Microsoft Store-style HTML interface prototype is available in
`web_gui/index.html`. Run `web_gui/Open Web GUI.bat` to preview it.

The current production app is still the Python/Tkinter version. The HTML GUI is
the planned frontend for a future Electron, Tauri, WebView2, or pywebview build.

## Editing

Use the **OCR Generator** tab to add images or a folder, inspect processed pages,
edit OCR text, export a searchable PDF, and open it directly in the **PDF Editor**
tab.

Choose a tool on the toolbar:

- **Change text:** click an existing text line, edit it in the dialog, and press OK.
- **Text box:** drag a rectangle, then enter the text and font size.
- **Line:** choose solid, dotted, or arrow, then drag from start to end.
- **Shapes:** choose rectangle, square, or circle and select edge/fill colours.
- **Image:** drag the destination rectangle, then select an image.
- **Select:** click an inserted object, drag inside it to move, or drag a yellow
  corner handle to resize. Use the object controls above the page to rotate or
  delete it.
- **Edit text:** select a text box and click **Edit text**, or double-click the
  text box directly.

Use **OCR pages** and enter page numbers such as `1,3-5` or `all`.
Press `Ctrl+Z` to undo.

Text replacement covers the original line with white and writes replacement
text using Helvetica. Complex layouts, unusual embedded fonts, transparency,
and text over non-white backgrounds can require manual cleanup.
