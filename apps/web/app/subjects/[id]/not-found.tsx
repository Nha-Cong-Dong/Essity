import { NotFoundBody } from "@/components/not-found-body";

// E-06: a subject that is not yours or does not exist. It renders inside the subject page's
// AppShell (the shell is already streamed), so only the body is here.
export default function SubjectNotFound() {
  return <NotFoundBody href="/subjects" label="Về danh sách môn học" />;
}
