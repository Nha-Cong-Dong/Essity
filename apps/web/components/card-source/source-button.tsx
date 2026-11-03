import { sourceHref } from "@/lib/card-source";

// G4: the "Nguồn" button of a card. Reusable: the vault card, the graph detail panel.
export function SourceButton({ cardId, className }: { cardId: string; className?: string }) {
  return (
    <a
      href={sourceHref(cardId)}
      className={
        className ??
        "inline-flex min-h-11 items-center rounded-full border border-line px-4 font-semibold underline-offset-2 hover:underline"
      }
    >
      Nguồn
    </a>
  );
}
