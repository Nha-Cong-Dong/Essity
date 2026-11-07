import { Mascot, type MascotPose } from "@/components/mascot";

/** MASCOT-BTN: one small cloud beside a page header. Decoration only; never covers content (it sits in the header row). */
export function HeadMascot({ pose }: { pose: MascotPose }) {
  return <Mascot pose={pose} size="sm" className="size-16 sm:size-24" />;
}
