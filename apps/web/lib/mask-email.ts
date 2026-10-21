// /check-email shows the address it wrote to, masked (DESIGN.md §6.1): "mi•••••@sv.edu.vn".
// At most two letters of the name, always five dots, so the length of the name stays hidden.
export function maskEmail(email: string): string {
  const at = email.lastIndexOf("@");
  const name = email.slice(0, at);
  const shown = name.length > 2 ? name.slice(0, 2) : name.slice(0, 1);
  return `${shown}•••••${email.slice(at)}`;
}
