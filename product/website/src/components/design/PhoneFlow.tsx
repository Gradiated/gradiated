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
            <span className="gr-phone-appname">Sable</span>
          </div>

          <div className="gr-phone-chat">
            <div className="gr-phone-greet">
              <p className="gr-phone-hello">Good morning, Maya</p>
              <div className="gr-phone-bankcard">
                <span className="gr-phone-bankcard-name">Sable</span>
                <span className="gr-phone-bankcard-chip" />
                <span className="gr-phone-bankcard-balance">
                  <i>Checking</i>$8,214.60
                </span>
                <span className="gr-phone-bankcard-num">•••• 4021</span>
              </div>
              <div className="gr-phone-chips">
                <span>Spending recap</span>
                <span>Pay rent</span>
                <span>Move to savings</span>
              </div>
            </div>

            <div className="gr-phone-msg gr-phone-msg--user">
              How&apos;s my spending this month?
            </div>

            <div className="gr-phone-typing">
              <i />
              <i />
              <i />
            </div>

            <div className="gr-phone-msg gr-phone-msg--bot">
              <span className="gr-phone-line gr-phone-line--a">
                You&apos;ve spent $2,340 so far — 12% under last month&apos;s
                pace.
              </span>
              <span className="gr-phone-line gr-phone-line--b">
                Dining is up $85; travel is down $210.
              </span>
              <span className="gr-phone-line gr-phone-line--c">
                At this rate you&apos;ll clear about $600 spare this month.
              </span>
            </div>

            <div className="gr-phone-card">
              <span className="gr-phone-card-dot" />
              <span>Move $500 to savings</span>
              <span className="gr-phone-card-go">Review</span>
            </div>
          </div>

          <div className="gr-phone-input">
            <span>Ask about your money</span>
            <span className="gr-phone-mic" />
          </div>
        </div>

        <div className="gr-phone-homebar" />
      </div>
    </div>
  </div>
);
