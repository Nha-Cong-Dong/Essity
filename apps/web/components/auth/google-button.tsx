import { Button } from "@/components/ui/button";
import { GOOGLE_SIGN_IN_ENABLED } from "@/lib/auth-flags";

function GoogleMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.5l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z" />
      <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}

/**
 * The Google button and the "hoặc" divider under it, as one piece: both go with the flag, so
 * nothing is left over (no empty gap) while Google is off.
 */
export function GoogleSection({ label }: { label: string }) {
  if (!GOOGLE_SIGN_IN_ENABLED) return null;
  return (
    <>
      <Button render={<a href="/api/auth/google" />} nativeButton={false} variant="secondary" className="w-full gap-2.5">
        <GoogleMark />
        {label}
      </Button>
      <p aria-hidden="true" className="m-0 flex items-center gap-3.5 text-small text-ink-soft before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line">
        hoặc
      </p>
    </>
  );
}
