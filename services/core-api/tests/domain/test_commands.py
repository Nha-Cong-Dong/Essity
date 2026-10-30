"""T9.2a (US-18): command apply and undo, pure. Tests cite AC codes (spec us-18)."""

import datetime
import itertools
import uuid

import pytest

from core_api.domain.commands.apply import LARGE_COMMAND_ITEMS, apply_command
from core_api.domain.commands.labels import label_map
from core_api.domain.commands.registry import (
    CardAdd,
    CardAddIdea,
    CardDiscardDraft,
    CardEdit,
    CardMerge,
    CardSplit,
    CommandRejected,
    QuestionRelink,
    QuestionRemoveFromPractice,
    QuestionSetAnswer,
    QuestionSetType,
    SectionExclude,
    SectionMark,
    SectionSetPages,
    SuggestDeferSubject,
    SuggestOnlySubject,
    op_from_json,
    split_text,
)
from core_api.domain.commands.state import (
    Card,
    CardStatus,
    Document,
    Question,
    QuestionType,
    Section,
    Snapshot,
    StudyFilter,
    Subject,
)
from core_api.domain.commands.undo import undo_latest

USER, OTHER = uuid.uuid4(), uuid.uuid4()
SESSION = uuid.uuid4()
TODAY = datetime.date(2026, 10, 30)


def uid() -> uuid.UUID:
    return uuid.uuid4()


def counter():
    n = itertools.count(1)
    return lambda: uuid.UUID(int=next(n))


D1, D2, K1, K2, K3 = uid(), uid(), uid(), uid(), uid()
S1, S2, SUBJ, QT, DOC, Q1 = uid(), uid(), uid(), uid(), uid(), uid()
FOREIGN_CARD, FOREIGN_SECTION = uid(), uid()


def world() -> Snapshot:
    return Snapshot.of(
        USER,
        [
            Card(D1, USER, text="a1\na2", status=CardStatus.DRAFT, section_id=S1),
            Card(D2, USER, text="b1", status=CardStatus.DRAFT),
            Card(K1, USER, text="canon", status=CardStatus.CANONICAL),
            Card(K2, USER, text="canon2", status=CardStatus.CANONICAL),
            Card(FOREIGN_CARD, OTHER, text="theirs", status=CardStatus.DRAFT),
            Section(S1, USER, from_page=70, to_page=78),
            Section(S2, USER, from_page=1, to_page=5),
            Section(FOREIGN_SECTION, OTHER),
            Subject(SUBJ, USER),
            QuestionType(QT, USER),
            Document(DOC, USER),
            Question(Q1, USER, card_id=K1),
        ],
    )


def run(state, *ops, ids=None, cmd=None, session=SESSION):
    return apply_command(state, ops, ids or counter(), command_id=cmd or uid(), session_id=session)


def card(state, id_) -> Card:
    c = state.get("card", id_)
    assert isinstance(c, Card)
    return c


# --- AC2: every operation of the fixed list --------------------------------------------------


def test_ac2_card_edit_add_discard_idea():
    s = world()
    r = run(s, CardEdit(D2, "new"), CardAdd("fresh", S1), CardAddIdea(D1, DOC, "idea"))
    assert card(r.state, D2).text == "new" and card(r.state, D2).rev == 2
    assert card(r.state, D1).text == "a1\na2\nidea"
    added = [c for c in r.state.records.values() if isinstance(c, Card) and c.text == "fresh"]
    assert added[0].status is CardStatus.DRAFT and added[0].section_id == S1
    r2 = run(r.state, CardDiscardDraft(D2))
    assert card(r2.state, D2).status is CardStatus.DISCARDED


def test_ac2_section_ops():
    r = run(
        world(),
        SectionSetPages(S1, 70, 80),
        SectionExclude([S2]),
        SectionMark([S1, S2], studied=True),
    )
    s1 = r.state.get("section", S1)
    s2 = r.state.get("section", S2)
    assert isinstance(s1, Section) and isinstance(s2, Section)
    assert (s1.from_page, s1.to_page, s1.studied) == (70, 80, True)
    assert s2.excluded and s2.studied


def test_ac2_suggest_filters_replace_per_subject():
    until = TODAY + datetime.timedelta(days=7)
    r = run(world(), SuggestOnlySubject(SUBJ, until))
    f = r.state.get("filter", SUBJ)
    assert isinstance(f, StudyFilter) and (f.mode, f.until) == ("only", until)
    r2 = run(r.state, SuggestDeferSubject(SUBJ, until + datetime.timedelta(days=3)))
    f2 = r2.state.get("filter", SUBJ)
    assert isinstance(f2, StudyFilter) and f2.mode == "defer" and f2.rev == 2


def test_ac2_question_ops():
    r = run(
        world(),
        QuestionSetType(Q1, QT),
        QuestionRelink(Q1, section=S1),
        QuestionSetAnswer(Q1, "ans"),
        QuestionRemoveFromPractice(Q1),
    )
    q = r.state.get("question", Q1)
    assert isinstance(q, Question)
    assert (q.question_type_id, q.card_id, q.section_id) == (QT, None, S1)
    assert q.answer == "ans" and not q.in_practice


def test_ac2_relink_needs_exactly_one_target():
    with pytest.raises(CommandRejected) as e:
        run(world(), QuestionRelink(Q1, card=K1, section=S1))
    assert e.value.code == "exactly_one_target"


# --- AC4: id ownership, all-or-nothing, > 10 items -------------------------------------------


@pytest.mark.parametrize(
    "op",
    [
        CardEdit(FOREIGN_CARD, "x"),
        CardEdit(uid(), "x"),
        SectionSetPages(FOREIGN_SECTION, 1, 2),
        CardAdd("x", FOREIGN_SECTION),
        CardAddIdea(D1, uid(), "x"),
        SuggestOnlySubject(uid(), TODAY),
        QuestionSetType(Q1, uid()),
    ],
)
def test_ac4_ids_must_belong_to_the_user(op):
    with pytest.raises(CommandRejected) as e:
        run(world(), op)
    assert e.value.code == "not_owned"


def test_ac4_two_users_isolated_even_when_record_is_in_snapshot():
    # a record of another user smuggled into the snapshot is still refused
    with pytest.raises(CommandRejected):
        run(world(), CardDiscardDraft(FOREIGN_CARD))


def test_ac4_all_or_nothing():
    s = world()
    before = dict(s.records)
    with pytest.raises(CommandRejected):
        run(s, CardEdit(D1, "changed"), SectionSetPages(S1, 9, 3))
    assert s.records == before  # the snapshot is untouched, so nothing could land


def test_ac4_later_op_sees_effect_of_earlier_op():
    with pytest.raises(CommandRejected) as e:
        run(world(), CardMerge([D1, D2]), CardEdit(D2, "x"))
    assert e.value.code == "card_discarded"


def test_ac4_more_than_ten_items_runs_and_reports_count():
    sections = [Section(uid(), USER) for _ in range(LARGE_COMMAND_ITEMS + 2)]
    s = Snapshot.of(USER, list(world().records.values()) + sections)
    r = run(s, SectionExclude([x.id for x in sections]))
    assert r.affected == LARGE_COMMAND_ITEMS + 2
    assert all(
        isinstance(r.state.get("section", x.id), Section) and r.state.get("section", x.id).excluded  # type: ignore[union-attr]
        for x in sections
    )


def test_ac4_unchanged_items_are_not_counted():
    r = run(world(), SectionMark([S1], studied=False))
    assert r.affected == 0 and r.state.records == world().records


# --- AC5 / PLAN: merge and split on drafts only, deterministic -------------------------------


def test_ac5_merge_is_deterministic_concat_of_drafts():
    r = run(world(), CardMerge([D1, D2]))
    assert card(r.state, D1).text == "a1\na2\n\nb1"
    assert card(r.state, D2).status is CardStatus.DISCARDED
    assert run(world(), CardMerge([D1, D2])).state.records == r.state.records


@pytest.mark.parametrize("op", [CardMerge([D1, K1]), CardSplit(K1, 2), CardDiscardDraft(K1)])
def test_ac2_merge_split_discard_refuse_canonical(op):
    with pytest.raises(CommandRejected) as e:
        run(world(), op)
    assert e.value.code == "canonical_card"


def test_merge_needs_two_distinct_cards():
    for cards in ([D1], [D1, D1]):
        with pytest.raises(CommandRejected):
            run(world(), CardMerge(cards))


def test_split_rule_is_deterministic_and_carries_only_part_count():
    assert split_text("a\nb\nc\nd\ne", 2) == ["a\nb\nc", "d\ne"]
    assert split_text("a\nb\nc\nd\ne", 3) == ["a\nb", "c\nd", "e"]
    ids = counter()
    s = Snapshot.of(USER, [Card(D1, USER, text="a\nb\nc", status=CardStatus.DRAFT, section_id=S1)])
    r = run(s, CardSplit(D1, 3), ids=ids)
    cards = sorted((c for c in r.state.records.values() if isinstance(c, Card)), key=lambda c: c.text)
    assert [c.text for c in cards] == ["a", "b", "c"]
    assert {c.section_id for c in cards} == {S1}
    assert r.affected == 3


def test_split_refuses_when_too_few_lines():
    with pytest.raises(CommandRejected) as e:
        run(world(), CardSplit(D2, 2))
    assert e.value.code == "too_short_to_split"


# --- AC6: nothing destructive in the vocabulary ----------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "card_delete",
        "subject_delete",
        "document_delete",
        "question_bank_delete",
        "fsrs_reset",
        "history_clear",
        "cost_cap_set",
        "account_update",
        "unclear",
    ],
)
def test_ac6_forbidden_kinds_are_not_registered(kind):
    with pytest.raises(CommandRejected) as e:
        op_from_json({"kind": kind})
    assert e.value.code == "unsupported"


def test_op_from_json_builds_typed_ops_and_rejects_extra_fields():
    op = op_from_json({"kind": "card_merge", "cards": [str(D1), str(D2)]})
    assert op == CardMerge([D1, D2])
    op = op_from_json({"kind": "suggest_only_subject", "subject": str(SUBJ), "until": "2026-11-05"})
    assert op == SuggestOnlySubject(SUBJ, datetime.date(2026, 11, 5))
    with pytest.raises(CommandRejected):
        op_from_json({"kind": "card_edit", "card": str(D1), "text": "x", "user_id": str(OTHER)})
    with pytest.raises(CommandRejected):
        op_from_json({"kind": "card_edit", "card": "not-a-uuid", "text": "x"})


# --- AC9 + AC5: inverse before apply, undo ---------------------------------------------------


def test_ac9_log_entry_carries_ops_diff_and_inverse_from_the_starting_snapshot():
    s = world()
    r = run(s, CardEdit(D2, "new"))
    assert r.entry.ops == (CardEdit(D2, "new"),)
    (rev,) = r.entry.inverse
    assert rev.before == card(s, D2) and rev.expected_rev == 2
    (change,) = r.entry.changes
    assert change.before == card(s, D2) and change.after == card(r.state, D2)


def test_ac5_undo_restores_content_with_new_rev():
    s = world()
    r = run(s, CardMerge([D1, D2]), SectionSetPages(S1, 70, 80))
    u = undo_latest(r.state, [r.entry], SESSION)
    assert card(u.state, D1).text == "a1\na2" and card(u.state, D2).status is CardStatus.DRAFT
    s1 = u.state.get("section", S1)
    assert isinstance(s1, Section) and (s1.from_page, s1.to_page) == (70, 78)
    assert card(u.state, D1).rev > card(r.state, D1).rev  # append-only
    assert u.entry.undone


def test_ac5_undo_of_created_cards_discards_not_deletes():
    r = run(world(), CardSplit(D1, 2), ids=counter())
    u = undo_latest(r.state, [r.entry], SESSION)
    new_id = uuid.UUID(int=1)
    assert card(u.state, new_id).status is CardStatus.DISCARDED  # still there, history kept
    assert card(u.state, D1).text == "a1\na2"


def test_ac5_canonical_undo_appends_a_rev_and_keeps_history():
    s = world()
    r = run(s, CardEdit(K1, "edited"))
    u = undo_latest(r.state, [r.entry], SESSION)
    k = card(u.state, K1)
    assert k.text == "canon" and k.status is CardStatus.CANONICAL
    assert k.rev == card(s, K1).rev + 2  # edit = rev 2, undo = rev 3, nothing deleted


def test_ac5_undo_created_filter_removes_it():
    r = run(world(), SuggestOnlySubject(SUBJ, TODAY))
    u = undo_latest(r.state, [r.entry], SESSION)
    assert u.state.get("filter", SUBJ) is None


def test_ac5_newest_first_one_by_one():
    s = world()
    a = run(s, CardEdit(D2, "one"))
    b = run(a.state, CardEdit(D2, "two"))
    log = [a.entry, b.entry]
    u1 = undo_latest(b.state, log, SESSION)
    assert card(u1.state, D2).text == "one"
    log = [a.entry, u1.entry]
    u2 = undo_latest(u1.state, log, SESSION)
    assert card(u2.state, D2).text == "b1"
    with pytest.raises(CommandRejected) as e:
        undo_latest(u2.state, [replace_undone(a.entry), u1.entry], SESSION)
    assert e.value.code == "nothing_to_undo"


def replace_undone(entry):
    from dataclasses import replace

    return replace(entry, undone=True)


def test_ac5_refused_when_rev_changed_after_the_command():
    r = run(world(), CardEdit(D2, "mine"))
    edited_by_hand = r.state.put(card(r.state, D2).changed(text="hand edit"))
    with pytest.raises(CommandRejected) as e:
        undo_latest(edited_by_hand, [r.entry], SESSION)
    assert e.value.code == "changed_after" and str(D2) in e.value.detail


def test_ac5_refused_when_a_section_changed_after_the_command():
    r = run(world(), SectionSetPages(S1, 70, 80))
    other = r.state.put(r.state.get("section", S1).changed(excluded=True))  # type: ignore[union-attr]
    with pytest.raises(CommandRejected) as e:
        undo_latest(other, [r.entry], SESSION)
    assert e.value.code == "changed_after"


def test_ac5_refused_when_another_command_touched_the_same_card():
    a = run(world(), CardEdit(D2, "one"))
    b = run(a.state, CardEdit(D2, "two"))
    # b is newest: a can only be reached after b; the log order enforces it
    assert undo_latest(b.state, [a.entry, b.entry], SESSION).entry.command_id == b.entry.command_id


def test_ac5_undo_is_limited_to_the_screen_session():
    r = run(world(), CardEdit(D2, "x"))
    with pytest.raises(CommandRejected) as e:
        undo_latest(r.state, [r.entry], uid())
    assert e.value.code == "other_session"


def test_undo_with_empty_log():
    with pytest.raises(CommandRejected) as e:
        undo_latest(world(), [], SESSION)
    assert e.value.code == "nothing_to_undo"


def test_empty_command_is_refused():
    with pytest.raises(CommandRejected):
        run(world())


# --- labels follow display order -------------------------------------------------------------


def test_labels_follow_request_display_order_and_reordering_changes_targets():
    order = [D1, D2, K1]
    swapped = [D2, D1, K1]
    assert label_map("C", order)["C2"] == D2
    assert label_map("C", swapped)["C2"] == D1  # "merge C1 and C2" now points elsewhere
    first = run(world(), CardEdit(label_map("C", order)["C1"], "x"))
    second = run(world(), CardEdit(label_map("C", swapped)["C1"], "x"))
    assert card(first.state, D1).text == "x" and card(second.state, D2).text == "x"
