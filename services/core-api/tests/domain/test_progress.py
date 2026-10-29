"""T5.5a (US-10): the progress numbers, pure. Page coverage is the union of the session ranges,
"vững" is recall >= 90%, "sẵn sàng" is Q1 tạm (PRD §8.1)."""

import csv
import io
import uuid
from datetime import UTC, date, datetime

from core_api.domain.progress import (
    READY_SHARE,
    SOLID_RECALL,
    CsvRow,
    SubjectProgress,
    UnitProgress,
    covered_pages,
    csv_text,
    readiness,
    study_weeks,
)

DOC_A, DOC_B = uuid.uuid4(), uuid.uuid4()


# US-10 AC2. Red when: overlapping or touching ranges are counted twice.
def test_us10_ac2_overlapping_ranges_are_one_union() -> None:
    ranges = [(DOC_A, 1, 10), (DOC_A, 5, 15), (DOC_A, 16, 20), (DOC_A, 30, 30)]
    assert covered_pages(ranges, {DOC_A: 100}) == 21


def test_us10_ac2_a_document_is_counted_on_its_own() -> None:
    ranges = [(DOC_A, 1, 10), (DOC_B, 1, 10)]
    assert covered_pages(ranges, {DOC_A: 50, DOC_B: 50}) == 20


def test_us10_ac2_ranges_are_cut_to_the_page_count_and_unknown_documents_ignored() -> None:
    ranges = [(DOC_A, 8, 20), (DOC_B, 1, 5)]
    assert covered_pages(ranges, {DOC_A: 10}) == 3
    assert covered_pages([], {DOC_A: 10}) == 0


def units(*recalls: float | None) -> list[UnitProgress]:
    return [UnitProgress(asked=r is not None, recall=r) for r in recalls]


# Q1 tạm. Red when: the threshold moved or ">=" became ">".
def test_q1_thresholds() -> None:
    assert (SOLID_RECALL, READY_SHARE) == (0.9, 0.85)


# US-10 AC5. Red when: "vững" counts a unit that was never asked.
def test_us10_ac5_solid_counts_recall_at_or_above_ninety_percent() -> None:
    result = readiness(units(0.9, 0.95, 0.89, None))
    assert (result.units, result.asked, result.solid) == (4, 3, 2)


# Q1 tạm. Red when: a never-asked unit does not block "ready".
def test_q1_ready_needs_every_unit_asked_and_85_percent_solid() -> None:
    assert readiness(units(*[0.95] * 17 + [0.5] * 3)).ready  # 17/20 = 85%
    assert not readiness(units(*[0.95] * 16 + [0.5] * 4)).ready  # 80%
    assert not readiness(units(*[0.95] * 19 + [None])).ready  # one never asked
    assert not readiness([]).ready  # nothing to be ready for


# US-10 AC5. Red when: skipped units reach the denominator.
def test_us10_ac5_skipped_units_are_reported_and_left_out() -> None:
    result = readiness(units(0.95, 0.95), skipped=3)
    assert (result.units, result.skipped, result.ready) == (2, 3, True)


def test_solid_percent_is_none_without_units() -> None:
    assert readiness([]).solid_percent is None
    assert readiness(units(1.0, 0.1)).solid_percent == 50


def day(year: int, month: int, d: int) -> date:
    return date(year, month, d)


def at(d: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, d, hour, minute, tzinfo=UTC)


# US-10 AC4. Red when: hours come from anything but ended_at - started_at, or weeks start on
# another day.
def test_us10_ac4_hours_per_week_by_learning_day() -> None:
    sessions = [
        (day(2026, 10, 19), at(19, 10), at(19, 11, 30)),  # Monday: 1.5 h
        (day(2026, 10, 25), at(25, 10), at(25, 10, 30)),  # Sunday, same week: 0.5 h
        (day(2026, 10, 26), at(26, 9), at(26, 10)),  # next Monday: 1 h
    ]
    weeks = study_weeks(sessions)
    assert [(w.week_start, w.hours) for w in weeks] == [
        (day(2026, 10, 19), 2.0),
        (day(2026, 10, 26), 1.0),
    ]


# US-10 AC4. Red when: an open session adds hours (no end yet) or hides a week of studying.
def test_us10_ac4_open_session_counts_the_week_but_adds_no_hours() -> None:
    weeks = study_weeks([(day(2026, 10, 27), at(27, 9), None)])
    assert [(w.week_start, w.hours) for w in weeks] == [(day(2026, 10, 26), 0.0)]


def test_study_weeks_empty() -> None:
    assert study_weeks([]) == []


def parse(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


# US-10 AC3. Red when: the header or the column count changes under the endpoint.
def test_us10_ac3_csv_has_header_and_one_line_per_row() -> None:
    rows = [CsvRow("week", "", "2026-10-19", "hours", "2.0")]
    assert parse(csv_text(rows)) == [
        ["section", "subject", "period", "key", "value"],
        ["week", "", "2026-10-19", "hours", "2.0"],
    ]


# US-10 AC3 + Bảo mật. Red when: a subject name starting with = runs as a formula in a sheet.
def test_us10_ac3_csv_defuses_formulas_in_text() -> None:
    out = parse(csv_text([CsvRow("subject", "=HYPERLINK(1)", "", "ready", "no")]))
    assert out[1][1] == "'=HYPERLINK(1)"
    out = parse(csv_text([CsvRow("subject", "+1", "", "k", "-5")]))
    assert out[1][1] == "'+1" and out[1][4] == "-5"  # a number stays a number


def test_us10_ac3_csv_quotes_commas_and_newlines() -> None:
    out = parse(csv_text([CsvRow("subject", 'Mạng, "máy"\ntính', "", "k", "v")]))
    assert out[1][1] == 'Mạng, "máy"\ntính'


def test_subject_progress_shape() -> None:
    subject = SubjectProgress(
        subject_id=uuid.uuid4(),
        name="Mạng",
        exam_date=day(2026, 12, 1),
        pages_covered=3,
        pages_total=10,
        readiness=readiness(units(0.95)),
        days_to_exam=40,
    )
    assert subject.readiness.ready
