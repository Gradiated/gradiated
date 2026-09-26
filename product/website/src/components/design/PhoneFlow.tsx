import type { ReactElement } from "react";

/**
 * The product mock: an iPhone running an assistant app, as a looping flow.
 *
 * Built in the stack rather than shipped as a video: CSS renders crisp at
 * any pixel density, loops without a seam or a decoder, and costs nothing
 * when offscreen. The choreography is one 10s master loop — greeting with
 * suggestion chips, a question sent, the assistant typing, the reply
 * arriving line by line with an action card, a held rest, then a soft
 * reset — every element keyed to percentages of the same clock so the
 * beats can never drift apart.
 *
 * The screen speaks iOS (system font stack, blue/grey bubbles, island,
 * home bar) because it plays a CUSTOMER's product — the thing whose
 * traffic feeds the diagram around it — not Gradiated's own chrome.
 */

export const PhoneFlow = (): ReactElement => (
  <div aria-hidden="true" className="gr-phone">
    <div className="gr-phone-frame">
      {/* the hardware is a supplied render (burgundy iPhone 18 Pro); the
          app screen is overlaid into its screen cutout, and the image's
          own black screen shows as the bezel gap at the corners */}
      <img alt="" className="gr-phone-hw" src="/assets/iphone-18-pro-burgundy.png" />
      <div className="gr-phone-screen">
        <div className="gr-phone-status">
          <span className="gr-phone-time">9:41</span>
          <span className="gr-phone-island" />
          <span className="gr-phone-gauges">
            <i className="gr-phone-signal" />
            <i className="gr-phone-batt" />
          </span>
        </div>

        <div className="gr-phone-app">
          <div className="gr-phone-head">
            <span className="gr-phone-avatar" />
            <span className="gr-phone-appname">Atlas</span>
          </div>

          <div className="gr-phone-chat">
            <div className="gr-phone-greet">
              <p className="gr-phone-hello">Good morning, Maya</p>
              <div className="gr-phone-chips">
                <span>Plan my day</span>
                <span>Standup recap</span>
                <span>Inbox brief</span>
              </div>
            </div>

            <div className="gr-phone-msg gr-phone-msg--user">
              Summarize today&apos;s standup
            </div>

            <div className="gr-phone-typing">
              <i />
              <i />
              <i />
            </div>

            <div className="gr-phone-msg gr-phone-msg--bot">
              <span className="gr-phone-line gr-phone-line--a">
                Shipping is on track for Friday.
              </span>
              <span className="gr-phone-line gr-phone-line--b">
                Two blockers cleared this morning — payments retries and the
                iOS build.
              </span>
              <span className="gr-phone-line gr-phone-line--c">
                One open item needs your call on pricing.
              </span>
            </div>

            <div className="gr-phone-card">
              <span className="gr-phone-card-dot" />
              <span>3 action items</span>
              <span className="gr-phone-card-go">View</span>
            </div>
          </div>

          <div className="gr-phone-input">
            <span>Message</span>
            <span className="gr-phone-mic" />
          </div>
        </div>

        <div className="gr-phone-homebar" />
      </div>
    </div>
  </div>
);
