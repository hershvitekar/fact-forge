import logging
import gc
import torch
from pathlib import Path


def parse_document(source_path: str):
    """
    Hybrid Parser: 
    1. Uses pdfplumber for fast, low-memory text extraction (Baseline).
    2. Uses Docling ONLY for high-fidelity Table extraction.
    3. Merges them to minimize Docling's memory footprint and involvement.
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
        logging.info("Stage 1: Extracting baseline text with pdfplumber...")
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
            logging.error("pdfplumber baseline extraction failed: %s", e)
            return document

        # --- STAGE 2: Targeted Table Extraction (Docling) ---
        logging.info("Stage 2: Targeted table extraction with Docling...")
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
            from docling.datamodel.base_models import InputFormat
            
            # Hardware and Threading configuration
            accel_options = AcceleratorOptions(num_threads=1, device=AcceleratorDevice.CPU)
            
            pipeline_options = PdfPipelineOptions()
            pipeline_options.accelerator_options = accel_options
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True 
            pipeline_options.images_scale = 0.4
            pipeline_options.generate_page_images = False
            pipeline_options.generate_table_images = False
            pipeline_options.generate_picture_images = False
            
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
            result = converter.convert(source_path)
            
            # Map Docling tables to pages
            page_tables = {}
            for item, level in result.document.iterate_items():
                if type(item).__name__ == "TableItem":
                    page_no = item.prov[0].page_no if (item.prov and len(item.prov) > 0) else 1
                    if page_no not in page_tables:
                        page_tables[page_no] = []
                    page_tables[page_no].append(item.export_to_markdown())

            # Stitch tables into the document
            full_text = ""
            current_offset = 0
            for page in document["pages"]:
                p_no = page["page_number"]
                if p_no in page_tables:
                    # Append tables at the end of the page text
                    table_text = "\n\n### Extracted Tables ###\n\n" + "\n\n".join(page_tables[p_no]) + "\n"
                    page["text"] += table_text
                
                page["start_offset"] = current_offset
                page["end_offset"] = current_offset + len(page["text"])
                full_text += page["text"]
                current_offset = page["end_offset"]
            
            document["text"] = full_text
            logging.info("Successfully stitched Docling tables into baseline text.")

            # Cleanup
            del converter
            gc.collect()
            if torch.cuda.is_available(): torch.cuda.empty_cache()

        except Exception as e:
            logging.warning("Docling table extraction skipped/failed: %s. Using baseline text only.", e)
            # Baseline is already in 'document', so we just continue
            gc.collect()

    return document
