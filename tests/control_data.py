"""Generate fictional text, DOCX and PDF inputs with expected demo scores."""
import csv
from pathlib import Path

from docx import Document
from reportlab.pdfgen import canvas

JOBS = {
    "backend": ("Python", "SQL"),
    "frontend": ("Flutter", "Dart"),
}


def build(root):
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for vacancy, terms in JOBS.items():
        (root / f"{vacancy}.txt").write_text("\n".join(terms), encoding="utf-8")
        for index in range(10):
            match = index % 4
            resume = [f"Fictional profile {vacancy} {index:02d}"]
            resume.extend(f"Project used {term}." for bit, term in enumerate(terms) if match & (1 << bit))
            extension = ("txt", "docx", "pdf")[index % 3]
            path = root / f"{vacancy}-{index:02d}.{extension}"
            if extension == "txt":
                path.write_text("\n".join(resume), encoding="utf-8")
            elif extension == "docx":
                document = Document()
                for line in resume:
                    document.add_paragraph(line)
                document.save(path)
            else:
                document = canvas.Canvas(str(path))
                for line_index, line in enumerate(resume):
                    document.drawString(50, 790 - 20 * line_index, line)
                document.save()
            manifest.append((vacancy, path.name, bool(match & 1), bool(match & 2), {0: 0, 1: 67, 2: 33, 3: 100}[match]))
    (root / "broken.pdf").write_bytes(b"not a pdf")
    (root / "oversize.txt").write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    scan = canvas.Canvas(str(root / "no-text.pdf"))
    scan.rect(50, 50, 200, 200, fill=1)
    scan.showPage()
    scan.save()
    with (root / "expected.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["vacancy", "filename", "first_confirmed", "second_confirmed", "rounded_score"])
        writer.writerows(manifest)
    return manifest


if __name__ == "__main__":
    build(Path("data/control"))
