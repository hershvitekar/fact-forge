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
            from docling.document_converter import DocumentConverter
            
            logging.info("Initializing Docling DocumentConverter...")
            converter = DocumentConverter()
            result = converter.convert(source_path)
            
            current_offset = 0
            page_texts = {}
            
            logging.info("Iterating over document items...")
            for item, level in result.document.iterate_items():
                page_no = 1
                if hasattr(item, 'prov') and item.prov and len(item.prov) > 0:
                    page_no = item.prov[0].page_no

                if page_no not in page_texts:
                    page_texts[page_no] = ""
                
                # Extract tables specifically as markdown to preserve structure
                if type(item).__name__ == "TableItem":
                    page_texts[page_no] += item.export_to_markdown() + "\n\n"
                elif hasattr(item, 'text') and item.text:
                    page_texts[page_no] += item.text + "\n\n"
                    
            for page_no in sorted(page_texts.keys()):
                page_text = page_texts[page_no]
                start_offset = current_offset
                end_offset = start_offset + len(page_text)
                
                document["pages"].append({
                    "page_number": page_no,
                    "text": page_text,
                    "start_offset": start_offset,
                    "end_offset": end_offset
                })
                document["text"] += page_text
                current_offset = end_offset
                
            logging.info("Extracted %d pages via Docling (Length: %d characters)", len(document["pages"]), len(document["text"]))
            
        except ImportError:
            raise RuntimeError("docling is required to parse PDF documents")
        except Exception as e:
            logging.error("Failed to parse PDF with docling: %s", e)

    return document
