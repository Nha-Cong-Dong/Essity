import { Mascot, type MascotPose } from "@/components/mascot";

/** MASCOT-BTN: one small cloud beside a page header. Decoration only; never covers content (it sits in the header row). Hidden under 360 px so the first screen keeps its content (graph frame at 320). */
export function HeadMascot({ pose }: { pose: MascotPose }) {
  return <Mascot pose={pose} size="sm" className="hidden size-16 min-[360px]:block sm:size-24" />;
}
