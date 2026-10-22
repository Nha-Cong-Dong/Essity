// A subject id that may go into a URL or a core-api path (review plan R1: "..", "/" never do).
// Plain, so both the browser and the server use it.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isSubjectId(id: unknown): id is string {
  return typeof id === "string" && UUID.test(id);
}
