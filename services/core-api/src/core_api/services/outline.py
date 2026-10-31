"""Outline application services (T7.4, US-01 AC5/AC7, US-13 AC4-AC6).

Each edit is one method that takes ids and plain values and raises a domain error, so the HTTP
routes and the command bar (T9.2) call the same code. Every query is scoped to the user the
service is built for; a document or section of another user is "not found". An edit locks the
document row FOR UPDATE, so two edits of one outline run one after the other.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core_api.db.models import DocSection, Document
from core_api.db.models.document import UNCONFIRMED
from core_api.domain import outline as rules
from core_api.domain.outline import RangeError, SectionRow
from core_api.repositories.doc_section import DocSectionRepository, NewSection
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository

__all__ = [
    "DocumentNotFoundError",
    "NameTakenError",
    "NoChangeError",
    "OutlineService",
    "OutlineView",
    "RangeError",
    "SectionNotFoundError",
    "SubjectNotFoundError",
    "TextbookExistsError",
    "TextbookHasCardsError",
    "TextbookNotReadyError",
]


class SectionNotFoundError(LookupError):
    """No such section for this user."""


class DocumentNotFoundError(LookupError):
    """No such document for this user."""


class NoChangeError(ValueError):
    """A patch that names nothing to change."""


class NameTakenError(ValueError):
    """Another document of the subject has this short name (US-01 AC7)."""


class TextbookExistsError(ValueError):
    """The subject already has a main textbook; replacing it is the learner's choice
    (US-01 AC5): nothing is overwritten."""


class TextbookNotReadyError(ValueError):
    """The document cannot be the textbook: its upload is not confirmed, was refused or failed."""


class TextbookHasCardsError(ValueError):
    """The textbook has live cards linked to its sections: changing it needs the learner's
    confirmation (`confirm`). `cards` is how many."""

    def __init__(self, cards: int) -> None:
        super().__init__(cards)
        self.cards = cards


@dataclass(frozen=True)
class OutlineView:
    document: Document | None
    sections: list[DocSection]
    progress: float
    section_progress: dict[uuid.UUID, float]
    excluded: set[uuid.UUID]


def _row(section: DocSection) -> SectionRow:
    return SectionRow(
        id=section.id,
        parent_id=section.parent_id,
        first_page=section.first_page or 0,  # NULL only on rows this code did not write
        last_page=section.last_page or 0,
        weight=section.weight,
        studied_weight=section.studied_weight,
        excluded=section.excluded,
    )


class OutlineService:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.documents = DocumentRepository(session, user_id)
        self.sections = DocSectionRepository(session, user_id)
        self.subjects = SubjectRepository(session, user_id)

    # --- reading -----------------------------------------------------------------------

    def textbook(self, subject_id: uuid.UUID) -> Document | None:
        return next(
            (
                d
                for d in self.documents.of_subject(subject_id)
                if d.role == "textbook" and d.status not in (*UNCONFIRMED, "failed")
            ),
            None,
        )

    def view(self, subject_id: uuid.UUID) -> OutlineView:
        """The outline of the subject's main textbook. SubjectNotFoundError for a subject that
        is not this user's; no textbook (or none read yet) is an empty view, not an error."""
        if self.subjects.get(subject_id) is None:
            raise SubjectNotFoundError
        document = self.textbook(subject_id)
        sections = [] if document is None else self.sections.of_document(document.id)
        rows = [_row(s) for s in sections]
        return OutlineView(
            document=document,
            sections=sections,
            progress=rules.progress(rows),
            section_progress=rules.section_progress(rows),
            excluded=rules.excluded_ids(rows),
        )

    # --- storing what indexing read ------------------------------------------------------

    def store_outline(self, document: Document, nodes: Sequence[NewSection]) -> bool:
        """Save the tree ai-service read. Idempotent: the same answer again leaves the same tree.
        An outline the learner has touched (an edit of theirs, covered pages, linked cards) is
        never replaced, whatever the new reading says. True when the tree was written."""
        if self.sections.touched(document.id):
            return False
        self.sections.replace(document.id, document.subject_id, nodes)
        return True

    # --- editing -------------------------------------------------------------------------

    def edit_section(
        self,
        section_id: uuid.UUID,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
        excluded: bool | None = None,
        studied: bool | None = None,
    ) -> DocSection:
        """Change one section: its range (both ends together), `excluded`, or `studied` (a leaf,
        or every leaf under a section). Raises SectionNotFoundError, NoChangeError, RangeError.
        A range or an exclusion makes the section the learner's (`source = user`): a later
        reading does not overwrite it. The range of a studied leaf keeps its coverage: fully
        covered stays fully covered, partly covered keeps what still fits."""
        if (first_page is None) != (last_page is None):
            raise RangeError("invalid_range")
        if first_page is None and excluded is None and studied is None:
            raise NoChangeError
        found = self.sections.get(section_id)
        if found is None or self.subjects.get(found.subject_id) is None:
            raise SectionNotFoundError
        document = self.documents.lock(found.document_id)
        if document is None:
            raise SectionNotFoundError
        sections = self.sections.of_document(document.id)
        by_id = {s.id: s for s in sections}
        section = by_id[section_id]
        rows = [_row(s) for s in sections]
        leaf_ids = {r.id for r in rules.leaves(rows)}

        if first_page is not None and last_page is not None:
            # A section without pages (not from an outline reading) has no range to edit.
            if any(s.first_page is None or s.last_page is None for s in sections):
                raise RangeError("invalid_range")
            rows = [_row(s) for s in sections]
            kids = [(r.first_page, r.last_page) for r in rows if r.parent_id == section.id]
            above = next((r for r in rows if r.id == section.parent_id), None)
            total = document.page_count or max(r.last_page for r in rows)
            rules.check_range(
                first_page,
                last_page,
                total,
                parent=None if above is None else (above.first_page, above.last_page),
                children=kids,
            )
            section.first_page, section.last_page = first_page, last_page
            section.source = "user"
            weights = rules.reweigh(rows, {section.id: (first_page, last_page)})
            for s in sections:
                old = s.weight
                s.weight = weights[s.id]
                if s.id in leaf_ids:
                    full = s.studied_weight >= old > 0
                    s.studied_weight = s.weight if full else min(s.studied_weight, s.weight)
        if excluded is not None:
            section.excluded = excluded
            section.source = "user"
        if studied is not None:
            for sid in rules.subtree_ids(rows, section.id):
                if sid in leaf_ids:
                    leaf = by_id[sid]
                    leaf.studied_weight = leaf.weight if studied else 0.0
        for s in sections:  # whatever an edit did, covered stays within 0..weight
            s.studied_weight = rules.clamp_studied(s.studied_weight, s.weight)
        self.session.flush()
        return section

    def set_textbook(
        self, subject_id: uuid.UUID, document_id: uuid.UUID, *, confirm: bool = False
    ) -> Document:
        """Make `document_id` the subject's main textbook (US-01 AC5). Raises
        SubjectNotFoundError, DocumentNotFoundError (not this subject's, or not this user's),
        TextbookNotReadyError, TextbookHasCardsError.

        The previous textbook becomes `auxiliary`. Nothing is deleted: its outline, the cards
        linked to it and its covered pages stay on that document, which is no longer the one
        the outline shows; the new textbook starts from its own outline. When the previous
        textbook has live cards linked to its sections the change needs `confirm`."""
        if self.subjects.get(subject_id) is None:
            raise SubjectNotFoundError
        target = self.documents.get(document_id)
        if target is None or target.subject_id != subject_id:
            raise DocumentNotFoundError
        self.documents.lock(document_id)
        if target.role == "textbook" and target.status not in (*UNCONFIRMED, "failed"):
            return target
        if target.status in (*UNCONFIRMED, "failed"):
            raise TextbookNotReadyError
        current = self.textbook(subject_id)
        if current is not None:
            cards = self.sections.linked_cards(current.id)
            if cards and not confirm:
                raise TextbookHasCardsError(cards)
            current.role = "auxiliary"
            self.session.flush()  # the one-textbook index: the old one goes first
        target.role = "textbook"
        self.session.flush()
        return target

    def edit_document(
        self,
        document_id: uuid.UUID,
        *,
        short_name: str | None = None,
        role: str | None = None,
    ) -> Document:
        """Change a document's short name (unique within its subject) or role. Raises
        DocumentNotFoundError, NoChangeError, NameTakenError, TextbookNotReadyError (the role
        `textbook` on a document not read), TextbookExistsError (the role
        `textbook` while another document of the subject is the main one: use
        `set_textbook` to replace it)."""
        if short_name is None and role is None:
            raise NoChangeError
        found = self.documents.get(document_id)
        if found is None or self.subjects.get(found.subject_id) is None:
            raise DocumentNotFoundError
        document = self.documents.lock(document_id)
        if document is None:
            raise DocumentNotFoundError
        if short_name is not None and short_name != document.short_name:
            taken = any(
                d.id != document.id and d.short_name.casefold() == short_name.casefold()
                for d in self.documents.of_subject(document.subject_id)
            )
            if taken:
                raise NameTakenError
            document.short_name = short_name
        if role is not None and role != document.role:
            if role == "textbook":
                if document.status in (*UNCONFIRMED, "failed"):
                    raise TextbookNotReadyError
                current = self.textbook(document.subject_id)
                if current is not None and current.id != document.id:
                    raise TextbookExistsError
            document.role = role
        self.session.flush()
        return document
