import logging
from pathlib import Path


def parse_document(source_path: str):
    """Parse a PDF or text document and return a normalized document object."""
    logging.info("Parsing document from %s", source_path)
    path = Path(source_path)
    document = {
        "source_path": str(path),
        "text": "",
        "pages": [],
    }

    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                current_offset = 0
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    # Add a newline between pages to keep offsets clean
                    if page_text:
                        page_text += "\n"
                        
                    start_offset = current_offset
                    end_offset = start_offset + len(page_text)
                    
                    document["pages"].append({
                        "page_number": i + 1,
                        "text": page_text,
                        "start_offset": start_offset,
                        "end_offset": end_offset
                    })
                    
                    document["text"] += page_text
                    current_offset = end_offset
                    
            logging.info("Extracted %d pages and %d characters", len(document["pages"]), len(document["text"]))
            
        except ImportError:
            raise RuntimeError("pdfplumber is required to parse PDF documents")
        except Exception as e:
            logging.error("Failed to parse PDF: %s", e)

    return document
