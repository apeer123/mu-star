import pdfplumber
import re
from pathlib import Path

pdf_path = Path("../../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book/Chapter 3/Schematic Diagrams and Flow Data/H02.pdf")
if not pdf_path.exists():
    pdf_path = Path("../../Downloads/Hydrology_Data_Book/Chapter 3/Schematic Diagrams and Flow Data/H02.pdf")

if pdf_path.exists():
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) >= 3:
            page = pdf.pages[2]
            text = page.extract_text()
            print("--- TEXT ---")
            print(text[:1000])
            blocks = re.split(r"(?i)\bDay\s+Nov\s+Dec", text)
            print("--- BLOCKS ---")
            print(len(blocks))
else:
    print("PDF not found")
