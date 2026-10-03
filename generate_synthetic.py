"""Generate a SYNTHETIC 12-month dataset of regulatory changes.

Everything here is invented for demonstration: titles, dates, agencies' "announcements".
Rows are flagged is_sample=1 and labelled "Sample" in the app and BI exports.
Tags (topic, impact, audience, action, deadline) are produced by the rule-based classifier
in classifier.py, so the dataset exercises the same tagging rules end to end.

Usage:
  python generate_synthetic.py            # replace sample rows with a fresh dataset
  python generate_synthetic.py --n 300    # different size
"""
import argparse
import random
from datetime import date, timedelta

import db
from classifier import classify

# Topic templates: (source choices, title, summary). {dl} = a future deadline date.
T = {
    "AML/CTF": [
        (["AUSTRAC"], "Reporting entities must update AML/CTF programs for new obligations",
         "Newly regulated professional services are required to enrol and update their AML/CTF program, including customer due diligence procedures, by {dl}. Civil penalty provisions apply."),
        (["AUSTRAC"], "Guidance published on suspicious matter reporting for {aud}",
         "Updated guidance clarifies when a suspicious matter report (SMR) should be lodged, with worked examples for {aud}."),
        (["AUSTRAC"], "Consultation opens on draft rules for customer due diligence",
         "AUSTRAC invites feedback on draft rules for customer due diligence and ongoing monitoring. Submissions close {dl}."),
        (["AUSTRAC"], "Enforcement action against a reporting entity for breach of the AML/CTF Act",
         "A civil penalty proceeding highlights failures in transaction monitoring and threshold transaction reporting."),
        (["AUSTRAC"], "Reminder: threshold transaction reports for cash of $10,000 or more",
         "A reminder of reporting obligations for reporting entities handling cash. Update your procedures."),
        (["AUSTRAC", "Law Society"], "Tranche 2 reforms: what {aud} need to prepare for",
         "Reforms extend AML/CTF obligations to lawyers, accountants and real estate agents. Businesses must prepare to enrol and appoint a compliance officer by {dl}. Mandatory."),
    ],
    "Superannuation": [
        (["ATO"], "Payday super: employers need to prepare for more frequent super guarantee payments",
         "Employers must pay super guarantee contributions more frequently. Payroll systems need to be ready before {dl}. Mandatory for all employers."),
        (["ATO"], "Super guarantee rate and maximum contribution base update",
         "The super guarantee rate and contribution base are updated for the new financial year. Employers must update payroll settings."),
        (["ATO"], "Stapled super funds: choice of fund reminder for new employees",
         "Onboarding employers must offer a stapled super fund where the employee has not chosen. Update onboarding documentation."),
        (["ATO"], "Unpaid superannuation: penalties and the super guarantee charge",
         "Employers who pay super late face the super guarantee charge and penalties. Lodge a statement by {dl}."),
    ],
    "Payroll": [
        (["ATO"], "Single Touch Payroll reporting reminder",
         "Employers are reminded to finalise STP data and check payroll withholding settings. Update software as required."),
        (["ATO", "Fair Work"], "Annual wage review: new minimum wage and modern award increases",
         "The Fair Work Commission announced increases to the national minimum wage and modern award wages, effective from {dl}. Employers must update payroll."),
        (["Fair Work"], "Modern award changes for clerks and legal services employees",
         "Changes to allowances and overtime rates in the clerks award. Employers need to review employee pay arrangements."),
        (["ATO"], "PAYG withholding: updated tax tables for the new year",
         "New PAYG withholding schedules apply for payroll from {dl}. Review your payroll software settings."),
    ],
    "Tax": [
        (["ATO"], "BAS lodgement due dates and common errors for tax agents and bookkeepers",
         "Reminder of upcoming BAS due dates. Lodge by {dl} to avoid penalties. Common deduction errors are listed."),
        (["ATO"], "GST treatment of residential property settlements",
         "Updated guidance for conveyancers and property sellers on GST withholding at settlement, including PEXA lodgement details."),
        (["ATO"], "Fringe benefits tax: draft guidance released",
         "A draft ruling is open for comment. This update does not change existing obligations."),
        (["ATO"], "Capital gains tax: reminder for property sellers",
         "Guidance on capital gains tax records for sellers. Accountants should review client records before lodging."),
    ],
    "Employment": [
        (["Fair Work"], "Casual employment: updated information statement requirements",
         "Employers must provide updated casual employment information to new casual employees."),
        (["Fair Work"], "Unfair dismissal: guidance for small business employers",
         "Plain-English guidance on the small business dismissal process and record keeping."),
        (["Fair Work"], "Enforcement: employer penalised for underpayment of employees",
         "A court imposed penalties after an employer breached workplace laws and underpaid employees. Employers must keep accurate records."),
        (["Fair Work"], "New leave entitlement rules for employees commence",
         "Changes to leave entitlements commence from {dl}. Employers need to review employee contracts and payroll."),
    ],
    "Trust Accounts": [
        (["Law Society"], "Trust account reminder: annual external examination and statutory deposit rules",
         "Legal practitioners operating a trust account must lodge the annual external examiner report by {dl}. Breach may lead to regulatory action."),
        (["Law Society"], "Trust money: guidance on receiving cash and third-party payments",
         "Legal practitioners should apply additional controls to trust money received from third parties, in line with AML expectations."),
        (["Law Society"], "Conveyancing risk update: settlement redirection scams",
         "Update on conveyancing fraud, settlement redirection scams and verification of identity steps for law firms."),
    ],
    "Privacy & Data": [
        (["OAIC"], "Notifiable data breaches report highlights legal and finance sectors",
         "Latest report shows a rise in notifiable data breaches from phishing and compromised credentials. Privacy obligations apply to professional services firms."),
        (["OAIC"], "Privacy Act amendments: strengthened penalties and new obligations",
         "Amendments introduce strengthened penalties and new obligations around data handling. Consultation on guidance to follow."),
    ],
    "Sanctions": [
        (["DFAT"], "Autonomous sanctions: new designations announced",
         "New designated persons and entities added to the consolidated list. Reporting entities must screen customers against the updated list."),
        (["DFAT"], "Sanctions compliance guidance for legal and accounting service providers",
         "Guidance on sanctions screening and PEP checks for service providers."),
    ],
}
AUD = ["law firms", "accountants", "real estate agents", "legal practitioners"]


def weights_for_month(m: date) -> dict:
    """Topic mix by calendar month, with AML/CTF rising toward the present."""
    w = {k: 1.0 for k in T}
    months_ago = (date.today().year - m.year) * 12 + date.today().month - m.month
    w["AML/CTF"] = 1.2 + 2.4 * max(0, (12 - months_ago)) / 12     # reform lead-up
    if m.month in (6, 7):
        w["Superannuation"] *= 2.4; w["Payroll"] *= 2.0              # new financial year
    if m.month in (6,):
        w["Employment"] *= 1.8                                       # annual wage review
    if m.month in (10, 11, 2, 5):
        w["Tax"] *= 1.8                                              # BAS quarters
    w["Trust Accounts"] *= 1.5 if m.month in (3, 4, 9) else 1.0
    return w


def build(n: int, seed: int = 42) -> list[dict]:
    rnd = random.Random(seed)
    today = date.today()
    start = today - timedelta(days=365)
    rows = []
    # month volume grows slightly over time
    months = []
    d = date(start.year, start.month, 1)
    while d <= today:
        months.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    vol = [1.0 + 0.08 * i for i in range(len(months))]
    total = sum(vol)
    for m, v in zip(months, vol):
        count = max(3, round(n * v / total))
        w = weights_for_month(m)
        topics, weights = list(w), list(w.values())
        for _ in range(count):
            topic = rnd.choices(topics, weights)[0]
            sources, title, summary = rnd.choice(T[topic])
            pub = m + timedelta(days=rnd.randint(0, 27))
            if pub > today or pub < start:
                pub = min(max(pub, start), today)
            aud = rnd.choice(AUD)
            dl = pub + timedelta(days=rnd.randint(14, 150))
            fmt = lambda s: s.format(aud=aud, dl=dl.strftime("%-d %B %Y"))
            title, summary = fmt(title), fmt(summary)
            rows.append(dict(source=rnd.choice(sources), published=pub, title=title, summary=summary))
    return rows


def load(conn, n: int = 200, seed: int = 42) -> int:
    db.clear_sample(conn)
    rnd = random.Random(seed + 1)
    added = 0
    for i, r in enumerate(build(n, seed)):
        tags = classify(r["title"], r["summary"], r["published"])
        item = {
            "id": db.make_id("synthetic-" + r["source"], f"{r['title']}#{i}", None),
            "published": r["published"].isoformat(),
            "source": r["source"], "title": r["title"], "summary": r["summary"],
            "link": None, "is_sample": 1, **tags,
        }
        if db.upsert(conn, item):
            added += 1
            age = (date.today() - r["published"]).days
            if tags["action_req"]:
                if age > 75:
                    status = rnd.choices(["Actioned", "Reviewed"], [0.75, 0.25])[0]
                elif age > 30:
                    status = rnd.choices(["Actioned", "Reviewed", "New"], [0.35, 0.4, 0.25])[0]
                else:
                    status = rnd.choices(["New", "Reviewed"], [0.75, 0.25])[0]
            else:
                status = "Reviewed" if age > 14 else "New"
            db.set_status(conn, item["id"], status)
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    c = db.connect()
    print("generated", load(c, a.n, a.seed), "synthetic rows")
