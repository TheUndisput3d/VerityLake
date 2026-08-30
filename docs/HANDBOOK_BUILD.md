# Rebuilding the project handbook

The deliverable is `VerityLake_Complete_Project_Handbook.pdf`. Its editable sources are `PROJECT_HANDBOOK.md` and, for the implementation appendix, `END_TO_END_GUIDE.md`. The renderer supplies the cover, architecture diagram, clickable contents, bookmarks, tables, and page numbering.

Run from the project root with a separate documentation environment:

```bash
python3 -m venv /tmp/veritylake-pdf-env
/tmp/veritylake-pdf-env/bin/pip install reportlab==5.0.1
/tmp/veritylake-pdf-env/bin/python docs/build_handbook_pdf.py
```

The renderer uses DejaVu fonts from `/usr/share/fonts/truetype/dejavu`; adjust `FONT_DIR` for another system. ReportLab is a documentation dependency and is not added to the application's requirements or Docker images. The renderer supports the Markdown constructs used in these two source documents, rather than acting as a general Markdown implementation.

Validation performed for this edition: successful PDF parsing, text extraction, all 28 interview questions present, all chapter headings present, clickable table-of-contents annotations and outline destinations present, plus visual inspection of representative rendered pages. This verifies the document, not application runtime readiness.
