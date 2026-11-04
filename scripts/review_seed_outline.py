"""`python scripts/review_seed_outline.py PDF OUT.json`: the real outline of a textbook PDF.

Runs ai-service's own indexing steps (read the PDF, build the syllabus with no model) and writes
the `outline.json` that `core_api.cli_review_account --outline` takes. Run it from
`services/ai-service` (its environment). Reads the PDF only; prints the page count and node count.
"""

import json
import sys
from pathlib import Path

from ai_service.pdf import PdfLimits, open_pdf
from ai_service.tasks.syllabus import SyllabusPrompt, build_syllabus, outline_file


def _no_model(prompt: SyllabusPrompt) -> str:
    raise RuntimeError("no model")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: review_seed_outline.py PDF OUT.json", file=sys.stderr)
        return 2
    data = Path(argv[0]).read_bytes()
    with open_pdf(data, limits=PdfLimits()) as pdf:
        count = pdf.page_count
        outline = pdf.get_outline()
        pages = [pdf.extract_text(index) for index in range(count)]
    nodes = build_syllabus(count, outline, pages, _no_model)
    Path(argv[1]).write_text(
        json.dumps(outline_file(nodes), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"pages={count} nodes={len(nodes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
