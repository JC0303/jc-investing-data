# Strategy adjudication policy

一句話：這份文件決定一個策略什麼時候算有效、什麼時候該殺掉。
門檻必須在跑回測**之前**就定好。結果不好不能改門檻，只能記錄下來另開新假設。

Status: PROPOSED (awaiting JC's approval)
Version: v1 — drafted 2026-11-21
Applies to: every short-term or screening strategy backtested in this repo.

---

## 1. Why this exists

Three generations of short-term rules have been tested (v2 revenue momentum,
v3 reversal, v4 grid). Each was evaluated after the numbers were known. Without
a threshold fixed in advance, a losing result invites one more parameter tweak,
and the generation count grows without the evidence improving.

This policy fixes the bar first. The adjudicator script applies it mechanically.

## 2. Primary metric

Mean excess return per trade versus 0050 over the same holding window,
with a t-statistic clustered by signal date or signal week.

Raw return is not the metric. Beating 0050 is the metric, because 0050 is the
alternative that requires no work and carries no execution risk.

## 3. Verdicts

The adjudicator emits exactly one verdict per strategy.

### KILL — stop work on this rule
Any one of these is enough:
- clustered t <= 0
- mean excess <= 0 over the full sample
- mean excess after removing the top 5% of trades < 0, while clustered t < 2.0
- the rule has already been revised twice (see section 5) and still fails PROMOTE

### INSUFFICIENT — keep collecting, do not act
- fewer than 200 trades, or
- holdout period shorter than 6 months, or
- fewer than 2 distinct calendar years in the sample

INSUFFICIENT is not a pass. No money moves on an INSUFFICIENT verdict.

### PROMOTE — eligible for paper tracking
All of these must hold:
- clustered t >= 2.0
- mean excess > 0 after removing the top 5% of trades
- mean excess > 0 in the holdout period, evaluated separately
- at least 200 trades across at least 2 calendar years

PROMOTE means paper tracking only. It never means place an order.
Real money requires a separate, explicit decision by JC, recorded with its date.

## 4. Applying v1 to what already exists

Recorded for the record; these are the numbers already in results/, not a re-run.

| Strategy | clustered t | mean excess | trimmed (ex top 5%) | Verdict under v1 |
|---|---|---|---|---|
| A-track historical check | -1.40 | -0.252% | -1.483% | KILL |
| v3 reversal | -2.82 | -0.351% | -1.595% | KILL |
| v2 revenue momentum | 1.92 | +0.335% | -1.418% | KILL |

All three fail. That is the expected outcome of a bar set honestly, and it is
the point of the policy: it says so in one line instead of inviting a v5.

## 5. Revision limit

A hypothesis may have its parameters revised at most twice. A third attempt
is only allowed as a NEW hypothesis, which requires, written before the run:
- what economic reason is expected to make it work
- what result would falsify it

Grid searches over many parameter combinations count as one revision, and the
in-sample best must be reported alongside its out-of-sample result. An
in-sample grid winner with no holdout result is INSUFFICIENT by definition.

## 6. Changing this policy

Thresholds may be changed, but never in the same session as a result that
would be affected by the change. Any change records: the old value, the new
value, the reason, and the date. The adjudicator refuses to run if the policy
file was modified more recently than the backtest it is judging.

## 7. What this policy does NOT cover

- 0050 monthly DCA and the extra-contribution ladder: core holdings, governed
  by JC's own rules, not by backtest verdicts.
- Individual holdings already bought: governed by their own review lines.
- Anything requiring a buy or sell order. Claude never places orders.
