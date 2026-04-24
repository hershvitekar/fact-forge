import sys
import os
import json
import shutil
from pathlib import Path
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

def process_pdf(pdf_file_path):
    # Setup Paths
    input_path = Path(pdf_file_path).resolve()
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return

    # Define Output Dirs relative to the data folder
    # Expected structure: data/pdfs/file.pdf -> data/markdown/file.md
    data_dir = input_path.parents[1]
    md_dir = data_dir / "markdown"
    out_dir = data_dir / "outputs"
    arc_dir = data_dir / "archive"

    # Optimization for i5 7th Gen (2-core) & 12GB RAM
    options = PdfPipelineOptions()
    options.do_ocr = False                 # Native PDFs only
    options.num_threads = 2                # Prevent CPU thrashing
    options.table_structure_options.mode = "accurate" # Institutional-grade tables

    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=options)}
    )

    print(f"[*] Processing: {input_path.name}")
    
    try:
        # Perform Conversion
        result = converter.convert(input_path)
        
        # Save Markdown
        md_file = md_dir / f"{input_path.stem}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(result.document.export_to_markdown())
        
        # Extract Tables for Graph Nodes
        tables_data = []
        for i, table in enumerate(result.document.tables):
            tables_data.append({
                "table_index": i,
                "page_no": table.prov[0].page_no if table.prov else None,
                "data": table.export_to_dict()
            })
        
        json_file = out_dir / f"{input_path.stem}_tables.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(tables_data, f, indent=2)

        # Move to Archive
        shutil.move(str(input_path), str(arc_dir / input_path.name))
        
        print(f"[+] Success: {input_path.name} converted and archived.")

    except Exception as e:
        print(f"[FAILED] Error processing {input_path.name}: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py <path_to_pdf>")
    else:
        process_pdf(sys.argv[1])