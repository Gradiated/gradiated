import type { CSSProperties, ReactElement } from "react";

/**
 * The product mock: a supplied full-device render — an Apple-Card-style
 * wallet screen in its own iPhone frame — standing in for the customer
 * product whose traffic feeds the loop diagram.
 *
 * It enters with the page's one entrance gesture (gr-enter: rise, sharpen
 * from blur), a beat after the card that holds it; the card's overflow
 * crops the device's lower third, same as the coded phone did.
 *
 * The previous incarnation — the app built in CSS with a 10s looping
 * choreography — lives in git history (see 27857b02) if the mock ever
 * needs to animate again.
 */

export const PhoneFlow = (): ReactElement => (
  <div aria-hidden="true" className="gr-phone">
    <img
      alt=""
      className="gr-phone-render gr-enter"
      src="/assets/phone-app-screen.png"
      style={{ "--enter-delay": "0.45s" } as CSSProperties}
    />
  </div>
);
