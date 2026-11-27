"""Write latency_cases.json: five representative decision requests of different sizes and question mixes.

Long inputs are assembled from a fixed pool of sentences with a seeded generator, so the file is reproducible.
Usage: python make_latency_cases.py OUT.json
"""
import json
import random
import sys

rng = random.Random(7)

CONTRACT = [
    "The Supplier shall provide the Services in accordance with the Service Levels set out in Schedule 2.",
    "Either party may terminate this Agreement for convenience on ninety (90) days' written notice to the other party.",
    "The Customer shall pay each undisputed invoice within thirty (30) days of receipt.",
    "Neither party's aggregate liability under this Agreement shall exceed the fees paid in the twelve (12) months "
    "preceding the claim.",
    "The Supplier shall maintain insurance with a reputable insurer in an amount not less than five million dollars.",
    "All Intellectual Property Rights in the Deliverables shall vest in the Customer upon payment in full.",
    "The Supplier may not subcontract any of its obligations without the Customer's prior written consent.",
    "Confidential Information shall not include information that is or becomes publicly available through no fault "
    "of the receiving party.",
    "This Agreement is governed by the laws of the State of New York, and the parties submit to the exclusive "
    "jurisdiction of its courts.",
    "The Supplier shall process Personal Data only on documented instructions from the Customer.",
    "Fees are fixed for the Initial Term and may thereafter be increased by no more than the change in CPI.",
    "Any amendment to this Agreement must be in writing and signed by authorised representatives of both parties.",
]
INCIDENT = [
    "At 02:14 UTC the on-call engineer was paged for elevated 5xx rates on the checkout service.",
    "Error rates rose from a baseline of 0.2% to 7.8% within four minutes of the deploy.",
    "The deploy included a change to the connection pool size of the payments client.",
    "Database CPU on the primary replica stayed below 40% throughout the incident.",
    "Retries from the mobile clients amplified load on the payments gateway by roughly three times.",
    "The team rolled back the deploy at 02:41 UTC, and error rates returned to baseline by 02:49 UTC.",
    "Approximately 3,200 checkout attempts failed during the window; no payments were double-charged.",
    "A canary stage existed but was configured to promote automatically after five minutes.",
    "Alerting fired correctly, but the runbook linked from the alert pointed to a deprecated dashboard.",
    "Customer support received 141 tickets related to failed checkouts during the incident.",
    "Follow-up actions include making canary promotion manual for changes to payment clients.",
    "The connection pool limit was reduced from 200 to 20 by a typo in the configuration file.",
    "Synthetic monitoring in the EU region detected the failures two minutes before the page.",
    "No data was lost, and all failed orders were left in a recoverable state.",
]


def paragraphs(pool, n_sentences, per_paragraph=5):
    sentences = [rng.choice(pool) for _ in range(n_sentences)]
    return "\n\n".join(" ".join(sentences[i:i + per_paragraph]) for i in range(0, len(sentences), per_paragraph))


cases = [
    {"name": "moderation", "description": "One forum comment, one yes/no question (~150 tokens)",
     "state": {"forum": "Home espresso", "comment": "Honestly if you can't dial in a grinder after a week you "
               "probably shouldn't own one. Read the manual, it's not rocket science. Anyway the Niche is fine."},
     "questions": {"violates": {"type": "noul", "instructions": "Does this comment break a community rule against "
                                "personal attacks or harassment?"}}},
    {"name": "tool-routing", "description": "A short chat and five tools, one yes/no question per tool (~500 tokens)",
     "state": {"messages": [
         {"role": "system", "content": "You are a travel assistant. Tools: search_flights(origin, destination, "
                                       "date), rebook(booking_id, flight_id), send_sms(to, text), "
                                       "get_weather(city, date), cancel_booking(booking_id)."},
         {"role": "user", "content": "BA 2491 to Edinburgh just got cancelled. Get me on the next flight tonight if "
                                     "there is one, and text Sam that I'll be late for dinner. Booking ref is "
                                     "XK7Q2P."}]},
     "questions": {t: {"type": "noul", "instructions": f"Should the assistant call {t} to handle this request?"}
                   for t in ("search_flights", "rebook", "send_sms", "get_weather", "cancel_booking")}},
    {"name": "support-triage", "description": "A customer email, three questions of different types (~1,000 tokens)",
     "state": {"from": "dana.k@example.com", "subject": "Charged twice and still no access",
               "body": paragraphs([
                   "I upgraded to the Business plan on Monday and my card was charged twice for the same amount.",
                   "Since then none of my team can log in; we get an error saying the workspace is suspended.",
                   "We have a client presentation on Thursday and all our files are in the shared workspace.",
                   "I have already tried resetting my password and clearing the browser cache.",
                   "Your chatbot told me to wait 48 hours, which is not acceptable for a paying customer.",
                   "Please refund the duplicate charge and restore access as soon as possible.",
                   "Our account ID is 88-41-207 and the invoice numbers are INV-55120 and INV-55121.",
               ], 28)},
     "questions": {
         "queue": {"type": "choice", "instructions": "Which queue should handle this email?",
                   "criteria": {"billing": "Charges, refunds and invoices", "access": "Login and account access",
                                "technical": "Bugs and outages", "sales": "Plans and upgrades"}},
         "urgency": {"type": "score", "instructions": "How urgent is this email?",
                     "criteria": ["Can wait a week", "Within two days", "Today", "Within the hour"]},
         "refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"}}},
    {"name": "contract-review", "description": "A services agreement, two questions (~3,000 tokens)",
     "state": {"document": "Master Services Agreement", "text": paragraphs(CONTRACT, 150)},
     "questions": {
         "termination": {"type": "choice", "instructions": "What notice does a party need to terminate for "
                                                           "convenience?",
                         "criteria": {"none": "Termination for convenience is not allowed", "30": "30 days",
                                      "60": "60 days", "90": "90 days"}},
         "liability_cap": {"type": "noul", "instructions": "Does the agreement cap either party's liability?"}}},
    {"name": "incident-report", "description": "A long incident report, one question (~8,000 tokens)",
     "state": {"title": "Checkout outage postmortem", "report": paragraphs(INCIDENT, 420)},
     "questions": {"data_loss": {"type": "noul", "instructions": "Did the incident cause any data loss?"}}},
]
json.dump(cases, open(sys.argv[1], "w"), indent=1)
