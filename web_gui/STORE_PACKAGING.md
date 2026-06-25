# Open PDF Web GUI Packaging Plan

This folder is a dependency-free HTML prototype for the next Open PDF user
interface. It is meant to become the frontend for a Microsoft Store-ready
desktop app.

## Recommended App Shape

Use a desktop web shell:

- **Frontend:** HTML/CSS/JavaScript from `web_gui/`
- **PDF preview:** PDF.js in the next pass
- **Desktop wrapper:** Electron or WebView2/Tauri
- **Backend:** keep the current Python/PyMuPDF/Tesseract engine as a local worker
- **Store package:** MSIX

## Microsoft Store Notes

For a professional Store submission, plan for:

- App name, icon family, splash image, screenshots, and privacy text
- MSIX package identity and signing certificate
- No admin requirement for normal use
- Local-only document processing statement
- Clean uninstall behavior
- App data stored in user profile, not beside `Program Files`

## Next Engineering Step

Connect the UI to the Python engine through one of these routes:

1. Electron + local Python subprocess with JSON-RPC over stdin/stdout.
2. WebView2/Tauri shell + small localhost backend.
3. Python `pywebview` for a lighter wrapper while retaining Python packaging.

For Open PDF, option 1 is the most flexible and the most familiar for Store
packaging. Option 3 is smaller and faster to migrate from the existing app.
