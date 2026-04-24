import logging
from pathlib import Path


def parse_document(source_path: str):
    """
    Primary Parser:
    Uses pdfplumber for fast, low-memory text extraction from PDF documents.
    """
    logging.info("Parsing document from %s", source_path)
    path = Path(source_path)
    document = {
        "source_path": str(path),
        "text": "",
        "pages": [],
    }

    if path.suffix.lower() == ".pdf":
        # --- STAGE 1: Baseline Text Extraction (pdfplumber) ---
        logging.info("Extracting text with pdfplumber...")
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                current_offset = 0
                for i, page in enumerate(pdf.pages):
                    raw_text = page.extract_text() or ""
                    
                    # Safety-split: pdfplumber sometimes merges tables into giant lines 
                    # that cause NLP truncation. We split lines that are too long.
                    processed_lines = []
                    for line in raw_text.split("\n"):
                        if len(line) > 500:
                            # Split by common delimiters if the line is massive
                            sublines = line.replace("  ", "\n").split("\n")
                            processed_lines.extend([s.strip() for s in sublines if s.strip()])
                        else:
                            processed_lines.append(line)
                    
                    page_text = "\n".join(processed_lines)
                    if page_text:
                        page_text += "\n"
                    
                    document["pages"].append({
                        "page_number": i + 1,
                        "text": page_text,
                        "start_offset": current_offset,
                        "end_offset": current_offset + len(page_text),
                    })
                    document["text"] += page_text
                    current_offset += len(page_text)
        except Exception as e:
            logging.error("pdfplumber extraction failed: %s", e)
            return document

    return document
