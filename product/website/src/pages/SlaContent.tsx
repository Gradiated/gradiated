import type { ReactElement } from "react";
import { SiteLink } from "../components/SiteLink";

export const SlaContent = (): ReactElement => (
  <>
    <p>Effective date: October 4, 2026</p>
    <p>
      This Service Level Agreement (SLA) describes the availability commitment
      that Gradiated, a division of PostHog Inc., makes for paid inference and
      the credits you can claim if we miss it. It forms part of our{" "}
      <SiteLink href="/terms/">Terms of Service</SiteLink>. A separate agreement
      signed with Gradiated takes precedence where its SLA terms differ.
    </p>
    <h2>Our uptime target and commitment</h2>
    <p>
      Our general operating target is 99.9% monthly uptime for production
      inference. The contractual commitment under this SLA is 99.5%, with usage
      credits determined by the thresholds below.
    </p>
    <p>
      We commit to 99.5% monthly uptime for each production model served through
      the Gradiated inference API. This SLA covers direct paying customers,
      including prepaid and invoiced accounts. Free services, models expressly
      marked beta or experimental, training, the website and the console are
      outside its scope. If you buy access through a reseller, claims go through
      that reseller under your agreement with them.
    </p>
    <h2>How we measure uptime</h2>
    <p>
      We measure each model separately for your organization over a calendar
      month in UTC. For each five-minute interval, availability is the
      percentage of eligible requests that did not fail because of Gradiated.
      Monthly uptime is the average of those interval percentages. An interval
      with no eligible requests counts as 100% available.
    </p>
    <p>
      An eligible request uses a supported inference endpoint and model, valid
      credentials and input, and stays within your account’s published or agreed
      limits. Failures include server errors (HTTP 5xx), inability to connect to
      our API, and responses that time out or stop before completing because of
      a fault in our service. For timeouts, the applicable limit is the
      documented API timeout or a timeout agreed with us in writing.
    </p>
    <p>
      We use our monitoring and request records together with evidence you
      provide to verify a claim. Deployment failures, routine maintenance and
      faults in infrastructure we use to deliver inference count when they cause
      covered requests to fail. This SLA covers availability; it does not
      promise a particular response speed or the accuracy of model outputs.
    </p>
    <h2>Usage credits</h2>
    <table>
      <thead>
        <tr>
          <th scope="col">Monthly uptime</th>
          <th scope="col">Usage credit</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>99.5% or higher</td>
          <td>None</td>
        </tr>
        <tr>
          <td>99% to below 99.5%</td>
          <td>5%</td>
        </tr>
        <tr>
          <td>95% to below 99%</td>
          <td>25%</td>
        </tr>
        <tr>
          <td>Below 95%</td>
          <td>100%</td>
        </tr>
      </tbody>
    </table>
    <p>
      The credit is that percentage of your net inference charges for the
      affected model during the 30 days immediately before the first covered
      outage in the affected month. A covered outage is an incident that causes
      eligible requests to fail. We use the same window for all incidents for
      that model in that month, so usage after the first outage cannot increase
      the credit. The window is 30 consecutive 24-hour periods, measured in UTC,
      ending at and excluding the outage’s start time.
    </p>
    <p>
      Net charges exclude taxes, refunds and promotional usage. Prepaid deposits
      are counted when spent on inference, not when added to your balance.
      Spending on other models or services is excluded.
    </p>
    <p>
      For example, if monthly uptime is 99.3% and your charges for the model in
      that 30-day window were $1,000, you receive a $50 usage credit. If you
      have used the model for fewer than 30 days, we use your actual charges in
      the window without extrapolating them. If you had no paid usage in the
      window, the credit is zero.
    </p>
    <p>
      We issue SLA compensation as usage credits added to the same
      organization’s Gradiated balance for future inference. They cannot be
      transferred or redeemed for cash. One credit band applies per model per
      month; bands and incidents do not stack. Total SLA credits for a model
      cannot exceed its net charges in that same 30-day window.
    </p>
    <h2>How to claim</h2>
    <p>
      Email <a href="mailto:team@gradiated.com">team@gradiated.com</a> with the
      subject “SLA credit claim” within 30 days after the affected month ends.
      Include your organization ID, model ID, month, incident times in UTC and
      any request IDs, error codes or connection logs you have. Do not send API
      keys, prompts, outputs or other private customer content.
    </p>
    <p>
      We will review the claim, explain our calculation and apply any confirmed
      credit within 30 days of receiving the information needed to verify it.
    </p>
    <h2>What is excluded</h2>
    <ul>
      <li>
        Invalid requests, authentication errors, exhausted balances, client
        cancellations and requests above your published or agreed limits.
      </li>
      <li>
        Failures caused by your application, equipment, configuration or
        internet connection outside Gradiated’s service boundary.
      </li>
      <li>
        Access suspended in accordance with our Terms, including for non-payment
        or misuse.
      </li>
      <li>
        Extraordinary events beyond our reasonable control, such as natural
        disasters, war or government orders. Ordinary failures of our hosting
        providers are not excluded on this basis.
      </li>
    </ul>
    <p>
      A capacity rejection within your published or agreed limits is not
      excluded just because it uses HTTP 429. If a Gradiated capacity fault
      causes it, we count it as a failure.
    </p>
    <h2>Relationship to our Terms</h2>
    <p>
      These credits are the remedy under this SLA for missing the availability
      commitment. Other provisions of our Terms continue to apply. Nothing here
      removes rights or remedies that the law does not allow us to limit.
    </p>
  </>
);
