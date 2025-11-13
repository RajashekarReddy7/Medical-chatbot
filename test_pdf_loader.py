import pdfplumber

pdf_path = "data/The-Gale-Encyclopedia-of-Medicine-3rd-Edition-staibabussalamsula.ac_.id_.pdf"  # Replace with your PDF file

try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"PDF loaded successfully! Total pages: {len(pdf.pages)}\n")
        
        # Only preview first 3 pages
        for i, page in enumerate(pdf.pages[:3]):
            try:
                text = page.extract_text()
                if text:
                    preview = text[:200]  # first 200 characters only
                    print(f"Page {i+1} preview:\n{preview}...\n")
                else:
                    print(f"Page {i+1} has no text.\n")
            except Exception as e:
                print(f"Error extracting page {i+1}: {e}\n")

except Exception as e:
    print(f"Failed to open PDF: {e}")
