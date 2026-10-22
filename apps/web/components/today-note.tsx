import { Button } from "@/components/ui/button";

// Plan K16: /today until T2.14 fills it with the day's session. It says what is true for the
// user: an invitation to create the first subject, or, once there is one, where the subjects are.
export function TodayNote({ hasSubjects }: { hasSubjects: boolean }) {
  if (!hasSubjects) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="m-0">Chưa có môn nào. Tạo môn đầu tiên bằng tên và ngày thi.</p>
        <Button render={<a href="/subjects/new" />} nativeButton={false}>
          Tạo môn
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="m-0" data-copy="tam">
        Lịch ôn hôm nay sẽ hiện ở đây sớm.
      </p>
      <Button render={<a href="/subjects" />} nativeButton={false} variant="secondary">
        Môn học
      </Button>
    </div>
  );
}
