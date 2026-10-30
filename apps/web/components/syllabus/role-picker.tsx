"use client";

import { useId } from "react";

import {
  IMAGE_NOT_MAIN,
  ROLE_HINT,
  ROLE_LABEL,
  type Role,
  type UploadFile,
} from "@/lib/syllabus/roles";

// T7.5a (US-01 AC4; DESIGN §6.4; design-decisions.md R2.5): three exclusive pills for the role of
// one file. Native radios, so Tab lands once and the arrow keys move between pills. An image cannot
// be the main syllabus: that pill is disabled for real (skipped by the arrows) and the reason is
// plain text under the group, not only a description.

const ROLES: Role[] = ["main", "bank", "supplementary"];

export function RolePicker({
  file,
  onPick,
}: {
  file: UploadFile;
  onPick: (role: Role) => void;
}) {
  const hintId = useId();
  const image = file.kind === "image";
  return (
    <div className="flex flex-col gap-2">
      <div
        role="radiogroup"
        aria-label={`Vai trò của ${file.name}`}
        aria-describedby={hintId}
        className="flex flex-wrap gap-2"
      >
        {ROLES.map((role) => {
          const blocked = image && role === "main";
          return (
            <label
              key={role}
              className="inline-flex h-11 cursor-pointer items-center rounded-full px-4 text-body font-semibold text-ink inset-ring-[1.5px] inset-ring-line-strong has-checked:bg-ink has-checked:text-bg has-checked:inset-ring-ink has-focus-visible:outline-2 has-focus-visible:outline-offset-3 has-focus-visible:outline-focus has-disabled:cursor-default has-disabled:bg-sunken has-disabled:inset-ring-line"
            >
              <input
                type="radio"
                name={`role-${file.id}`}
                value={role}
                checked={file.role === role}
                disabled={blocked}
                onChange={() => onPick(role)}
                className="sr-only"
              />
              {ROLE_LABEL[role]}
            </label>
          );
        })}
      </div>
      <p id={hintId} className="m-0 text-small text-ink-soft">
        {ROLE_HINT[file.role]}
        {image && <span className="block">{IMAGE_NOT_MAIN}</span>}
      </p>
    </div>
  );
}
