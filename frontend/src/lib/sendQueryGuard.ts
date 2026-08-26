/**
 * Synchronous in-flight slot for chat sends.
 *
 * React `status` updates are async, so the composer/form can still see
 * `idle` when Send is double-clicked or Enter is pressed twice in the
 * same tick. A ref claim here is the only reliable overlap guard.
 */
export function claimSendQuerySlot(inFlight: { current: boolean }): boolean {
  if (inFlight.current) return false;
  inFlight.current = true;
  return true;
}

export function releaseSendQuerySlot(inFlight: { current: boolean }): void {
  inFlight.current = false;
}
