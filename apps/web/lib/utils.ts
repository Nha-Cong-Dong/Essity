import { createCn } from "cn/config";

// The one class merger of the app. It must know the custom type steps, shadows and radii of
// app/globals.css: without them `text-read` is read as a colour and drops `text-on-hong` next to
// it (a pink button with an ink label). Components import `cn` from here, never from "cn".
export const TYPE_STEPS = [
  "meta",
  "body",
  "read",
  "answer",
  "lead",
  "question",
  "verdict",
  "title",
  "display",
  "mega",
  "hero",
  "logo",
  "caption",
  "small",
  "source",
  "hand",
  "section",
] as const;

export const cn = createCn({
  extend: {
    classGroups: {
      "font-size": [{ text: [...TYPE_STEPS] }],
      shadow: [{ shadow: ["sheet", "over", "cover", "hong", "elev", "panel", "book"] }],
      rounded: [{ rounded: ["control", "slip", "sheet", "tile"] }],
    },
  },
});
