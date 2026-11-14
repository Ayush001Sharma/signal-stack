"""Generate SYNTHETIC internal files used only to demonstrate the Internal Intelligence upload pipeline.

These files are NOT data from MeetUniversity, Razorpay or any real company. They are generated with a fixed
random seed so the demo is reproducible, and every filename starts with SYNTHETIC_DEMO_.
"""
import csv
import random
from pathlib import Path

from openpyxl import Workbook

random.seed(42)
out = Path(__file__).parent / "internal"
out.mkdir(exist_ok=True)

# --- Study-abroad counselling CRM export (synthetic) ---
dest = ["UK", "USA", "Canada", "Australia", "Ireland", "Germany"]
lost_reasons = ["too expensive", "went with competitor", "visa rejected", "chose to study in India", "no response after counselling", "too expensive"]
notes_lost = {
    "too expensive": ["Parent felt the counselling package is too expensive compared to free agents", "Budget concern: package price too expensive for the family", "Student said the fee is too expensive after loan EMI calculation"],
    "went with competitor": ["Went with a competitor that offered free application processing", "Chose an agent who promised faster offers from partner universities"],
    "visa rejected": ["Visa rejected after study permit cap; family worried about policy change", "Visa refusal due to funds documentation; student paused plans"],
    "chose to study in India": ["Decided to stay in India due to rupee depreciation and high living costs abroad"],
    "no response after counselling": ["No response after first counselling call; follow-up delays on our side"],
}
notes_won = [
    "Enrolled after visa guidance session; asked us to add accommodation search",
    "Converted after scholarship webinar; requested support for education loan comparison",
    "Happy with SOP review but complained about slow document review delays",
    "Converted; would like IELTS coaching integration with the application tracker",
    "Enrolled; document review was slow and caused delays before the deadline",
    "Converted after Ivy profile building sessions",
]
rows = []
for i in range(1, 49):
    won = random.random() < 0.42
    d = random.choice(dest)
    if won:
        rows.append({"lead_id": f"L{i:03d}", "created": f"2026-{random.randint(8, 10):02d}-{random.randint(1, 28):02d}", "destination": d, "program": random.choice(["Masters", "Undergraduate", "MBA"]),
                     "stage": "Closed Won", "lost_reason": "", "counsellor_notes": random.choice(notes_won)})
    else:
        r = random.choice(lost_reasons)
        if d == "Canada" and random.random() < 0.5:
            r = "visa rejected"
        rows.append({"lead_id": f"L{i:03d}", "created": f"2026-{random.randint(8, 10):02d}-{random.randint(1, 28):02d}", "destination": d, "program": random.choice(["Masters", "Undergraduate", "MBA"]),
                     "stage": "Closed Lost", "lost_reason": r, "counsellor_notes": random.choice(notes_lost[r])})
with open(out / "SYNTHETIC_DEMO_study_abroad_crm_export.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

(out / "SYNTHETIC_DEMO_counselling_call_notes.txt").write_text("""SYNTHETIC DEMO FILE - fictional call notes created to test the upload pipeline. Not real customer data.

Call 1: Student asked if we can add a cost-of-living calculator for UK cities. Concern that total cost is too expensive after the rupee fell.

Call 2: Parent worried about Canada study permit cap and asked whether a policy change could affect the January intake.

Call 3: Student frustrated that document review is slow; delays meant a missed scholarship deadline.

Call 4: Student would like accommodation search support near campus in Dublin.

Call 5: Family said a competitor offered free application processing; they are not sure our premium package is worth it.

Call 6: Student confused about post-study work visa rules in the UK and wants a clear guide.

Call 7: Parent asked for an education loan comparison; budget concern about EMI.

Call 8: Student said response time from counsellor was slow and follow-up was late.
""")

# --- Payments support tickets (synthetic) ---
wb = Workbook()
ws = wb.active
ws.append(["ticket_id", "merchant_segment", "category", "status", "message"])
msgs = [
    ("SMB", "settlement", "Settlement delayed by two days again, cash flow problem for our store"),
    ("SMB", "settlement", "Settlement delay issue, payout not received on time"),
    ("Enterprise", "integration", "Need a webhook integration with our ERP; please add retry logs"),
    ("Startup", "pricing", "MDR pricing is too expensive compared to other gateways"),
    ("SMB", "pricing", "Pricing too expensive for low ticket UPI transactions"),
    ("Enterprise", "compliance", "KYC re-verification request blocked onboarding; compliance documents rejected"),
    ("Startup", "integration", "Would like a Shopify plugin with subscription support"),
    ("SMB", "disputes", "Chargeback dispute process is confusing and slow"),
    ("SMB", "disputes", "Dispute resolution slow, issue still unresolved after a week"),
    ("Enterprise", "outage", "Payment failures during peak sale; outage hurt conversion"),
    ("Startup", "integration", "Need support for recurring payments via UPI Autopay API"),
    ("SMB", "settlement", "Payout stuck, settlement delayed with no clear status"),
]
for i, (seg, cat, m) in enumerate(msgs, 1):
    ws.append([f"T{i:03d}", seg, cat, random.choice(["open", "resolved"]), m])
wb.save(out / "SYNTHETIC_DEMO_payments_support_tickets.xlsx")
print("written", sorted(p.name for p in out.iterdir()))
