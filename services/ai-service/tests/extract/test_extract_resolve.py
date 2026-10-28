"""T4.10: printed page numbers and section labels become FILE pages, by code (US-02 AC3, Q7)."""

import pytest

from ai_service.tasks.extract_session import OutputViolation, Reference, resolve_pages
from tests.extract.helpers import docs_of, document, extract_body, printed_labels


def ref(
    kind: str = "pages",
    *,
    basis: str | None = "printed",
    from_page: int | None = None,
    to_page: int | None = None,
    from_section: str | None = None,
    to_section: str | None = None,
) -> Reference:
    return Reference(
        kind=kind,  # pyright: ignore[reportArgumentType]
        from_section=from_section,
        to_section=to_section,
        basis=basis,  # pyright: ignore[reportArgumentType]
        from_page=from_page,
        to_page=to_page,
    )


def book(**kwargs: object):
    return docs_of(extract_body(documents=[document(**kwargs)]))[0]  # pyright: ignore[reportArgumentType]


def test_ac3_pages_printed_to_file_with_labels() -> None:
    # Red when: "tr. 43-58" is taken as file pages (it is file 51-66).
    pages = resolve_pages(book(), ref(from_page=43, to_page=58))
    assert (pages.start, pages.end, pages.basis_assumed_file) == (51, 66, False)


def test_basis_file_is_not_converted() -> None:
    pages = resolve_pages(book(), ref(basis="file", from_page=51, to_page=66))
    assert (pages.start, pages.end, pages.basis_assumed_file) == (51, 66, False)


def test_printed_without_labels_is_taken_as_file_and_flagged() -> None:
    pages = resolve_pages(book(labels=None), ref(from_page=40, to_page=55))
    assert (pages.start, pages.end, pages.basis_assumed_file) == (40, 55, True)


def test_printed_number_with_no_label_is_taken_as_file_and_flagged() -> None:
    # 79 is not printed anywhere: the book ends at 72.
    pages = resolve_pages(book(), ref(from_page=70, to_page=79))
    assert (pages.start, pages.end, pages.basis_assumed_file) == (70, 79, True)


def test_one_end_matching_does_not_make_a_hybrid_range() -> None:
    # Review O2: "43-305" must not become 51..305; neither end is converted.
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(), ref(from_page=43, to_page=305))
    assert raised.value.rule == "x7"
    pages = resolve_pages(
        book(page_count=400, labels=printed_labels(400)), ref(from_page=43, to_page=305)
    )
    assert (pages.start, pages.end) == (51, 313)
    # An end with no label: the whole range stays as the learner said it, flagged.
    pages = resolve_pages(book(), ref(from_page=43, to_page=75))
    assert (pages.start, pages.end, pages.basis_assumed_file) == (43, 75, True)


def test_duplicate_printed_label_takes_first_at_or_after_start() -> None:
    # "1" is printed on file page 9 and again on an appendix page.
    labels = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii"] + [str(n) for n in range(1, 61)]
    labels += [str(n) for n in range(1, 13)]
    pages = resolve_pages(book(page_count=80, labels=labels), ref(from_page=1, to_page=12))
    assert (pages.start, pages.end) == (9, 20)


def test_section_span_runs_to_the_next_section_of_its_level() -> None:
    doc = book()
    # Chương 3 (S3, level 0) ends before Chương 4 (page 75).
    pages = resolve_pages(doc, ref("section", basis=None, from_section="D1.S3"))
    assert (pages.start, pages.end) == (51, 74)
    # 3.5 (level 1) ends before 3.6.
    pages = resolve_pages(doc, ref("section", basis=None, from_section="D1.S4"))
    assert (pages.start, pages.end) == (60, 69)
    # From 3.5 to 3.6 inclusive.
    pages = resolve_pages(doc, ref("section", basis=None, from_section="D1.S4", to_section="D1.S5"))
    assert (pages.start, pages.end) == (60, 74)


def test_last_section_runs_to_the_last_page() -> None:
    pages = resolve_pages(book(), ref("section", basis=None, from_section="D1.S6"))
    assert (pages.start, pages.end) == (75, 80)


@pytest.mark.parametrize("label", ["D1.S99", "D2.S1", "S1", "D1.", None, "D1.S0"])
def test_section_label_not_in_the_document_is_x4(label: str | None) -> None:
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(), ref("section", basis=None, from_section=label))
    assert raised.value.rule == "x4"


def test_continue_starts_after_the_last_session() -> None:
    pages = resolve_pages(book(last_end_page=50), ref("continue", basis="printed", to_page=60))
    assert (pages.start, pages.end) == (51, 68)
    pages = resolve_pages(book(last_end_page=50), ref("continue", basis=None, to_section="D1.S3"))
    assert (pages.start, pages.end) == (51, 74)


def test_continue_without_last_end_or_without_an_end_is_x8() -> None:
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(), ref("continue", basis="printed", to_page=60))
    assert raised.value.rule == "x8"
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(last_end_page=50), ref("continue", basis=None))
    assert raised.value.rule == "x8"


@pytest.mark.parametrize(
    ("basis", "start", "end"),
    [("file", 60, 81), ("file", 0, 5), ("file", 70, 60), ("file", -3, 5)],
)
def test_pages_out_of_range_are_x7(basis: str, start: int, end: int) -> None:
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(), ref(basis=basis, from_page=start, to_page=end))
    assert raised.value.rule == "x7"


def test_pages_reference_with_missing_numbers_is_x4() -> None:
    with pytest.raises(OutputViolation) as raised:
        resolve_pages(book(), ref(from_page=None, to_page=5))
    assert raised.value.rule == "x4"
