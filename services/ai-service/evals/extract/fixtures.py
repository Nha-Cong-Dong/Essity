"""Made-up documents for the extract eval, in the shape T4.7 writes (toc.json, page_labels.json).

`front` is the number of front-matter pages numbered in roman numerals; the page after them is
printed as 1. `labels="same"` prints the file's own numbers; `labels=None` has no labels at all.
"""

from dataclasses import dataclass
from typing import Literal

ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]


@dataclass(frozen=True)
class Book:
    short_name: str
    page_count: int
    toc: tuple[tuple[str, int, int | None], ...]  # (title, level, file page)
    front: int = 0
    labels: Literal["offset", "same"] | None = "offset"

    def page_labels(self) -> list[str] | None:
        if self.labels is None:
            return None
        if self.labels == "same":
            return [str(page) for page in range(1, self.page_count + 1)]
        return [
            ROMAN[page - 1] if page <= self.front else str(page - self.front)
            for page in range(1, self.page_count + 1)
        ]


BOOKS: dict[str, Book] = {
    # Printed number = file page - 8. Sections end before the next one of the same level or above:
    # Ch1 9-24 (1.1 10-15, 1.2 16-24), Ch2 25-50, Ch3 51-74 (3.5 60-69, 3.6 70-74), Ch4 75-80.
    "giaotrinh": Book(
        short_name="giáo trình",
        page_count=80,
        front=8,
        toc=(
            ("Chương 1 Giới thiệu", 0, 9),
            ("1.1 Internet", 1, 10),
            ("1.2 Mạng biên", 1, 16),
            ("Chương 2 Tầng ứng dụng", 0, 25),
            ("Chương 3 Tầng giao vận", 0, 51),
            ("3.5 Connection Management", 1, 60),
            ("3.6 Congestion Control", 1, 70),
            ("Chương 4 Tầng mạng", 0, 75),
        ),
    ),
    # Printed number = file page - 4. Ch1 5-16, Ch2 17-40 (2.1 18-29, 2.2 30-40), Ch3 41-60.
    "textbook": Book(
        short_name="textbook",
        page_count=60,
        front=4,
        toc=(
            ("Chapter 1 Introduction", 0, 5),
            ("Chapter 2 Probability", 0, 17),
            ("2.1 Random variables", 1, 18),
            ("2.2 Expectation", 1, 30),
            ("Chapter 3 Statistics", 0, 41),
        ),
    ),
    # Slides: no printed numbers. Bài 1 1-10, Bài 2 11-20, Bài 3 21-30, Bài 4 31-40.
    "slide": Book(
        short_name="slide",
        page_count=40,
        labels=None,
        toc=(
            ("Bài 1 Tổng quan", 0, 1),
            ("Bài 2 Ôn tập SQL", 0, 11),
            ("Bài 3 Chuẩn hóa", 0, 21),
            ("Bài 4 Giao dịch", 0, 31),
        ),
    ),
    # Exercise sheet: printed numbers equal the file's, no table of contents.
    "baitap": Book(short_name="bài tập", page_count=30, labels="same", toc=()),
}
