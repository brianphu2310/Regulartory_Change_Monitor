# Impact model: money, time and people

Version 1 of the monitor answers *which changes matter and who has to act*. The impact model adds the questions a
practice manager or finance lead asks next:

| Question | Answer from | Table |
|---|---|---|
| **Finance:** what will these changes cost us, once and every year? | Hours × loaded hourly cost + external spend | `change_impact`, `change_effort` |
| **Time:** how long do we have, and what is already late? | Target date, lead time, days left, at-risk flag | `change_impact` |
| **People:** who does the work, and do they have the hours? | Hours by role vs hours each role can give to regulatory work | `change_effort`, `capacity_monthly`, `dim_role` |

Build it with `python impact_model.py` after `python export_for_bi.py`. Everything is rule-based and deterministic, so
any figure can be traced back to one line of [`impact_model.py`](../impact_model.py).

## The rules

1. **Effort per topic.** Each topic has the one-off hours a *Medium* change needs (e.g. AML/CTF 12 h, Tax 4 h), an
   external cost (advice, software configuration, training) and a split of the hours across roles.
2. **Impact scales effort.** High × 2, Medium × 1, Low × 0.3. Only High-impact changes add ongoing hours and cost
   (a new obligation that recurs), because Medium and Low changes are mostly one-off updates.
3. **No action, little effort.** A change with no action required still costs 0.5 h for its owner to read and file it.
4. **Multi-topic changes** split their effort evenly across their topics, so nothing is counted twice.
5. **Money.** Internal cost = hours × the role's loaded hourly cost (salary, super and overheads). Total = internal + external.
6. **Time.** Target date = the stated deadline, or published + 30 / 60 / 90 days for High / Medium / Low when there is none.
   *At risk* = outstanding with fewer than 14 days left (overdue counts).
7. **People.** Outstanding hours are spread evenly over the months up to the target date; overdue work lands in the
   current month. Each role gives a fixed number of hours a month to regulatory work (Compliance Officer 40, others 10–16).

## Results on the synthetic data (as at 2 Oct 2026)

| Measure | Value |
|---|---|
| One-off cost of the year's changes | **$137K** ($104K internal time, $33K external) |
| New ongoing cost a year (High-impact changes) | **$23K** |
| Outstanding work | **473 hours** across 54 changes; 27 already past their target date |
| Backlog vs capacity | October needs **400 hours** against **140 hours** available: about three months of regulatory capacity |
| Most overloaded role | Compliance Officer: 119 hours needed in October against 40 available |

**What a partner should take from it:** the money is manageable; the people are not. The backlog sits mostly with the
Compliance Officer and the Principal, so the real decision is whether to bring in help for one quarter or accept that
lower-impact changes slip.

## Honest limits

- Hours, hourly costs, external costs and capacity are **assumptions** for a fictional small NSW firm, not benchmarks.
  They live in one place (`TOPICS`, `ROLES`) and are exported to `impact_assumptions.csv` and `dim_role.csv` so they can be
  challenged and changed.
- Effort is estimated per topic, not per change. A real assessment would size each change individually.
- The change data is synthetic, so the totals show the method, not a real firm's exposure.
