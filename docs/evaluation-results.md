# Evaluation results

This is the analysis of the first full live run: all 218 questions, 178 from templates and 40 held out, answered by `openai/gpt-oss-120b` on Groq and scored against the oracle. How the questions and metrics work is in [evaluation](evaluation.md).

The run was spread over three nights on the free tier, which allows 200,000 tokens a day, and a full run takes about 550,000. Each night resumed from the recorded responses. It finished on 30 October 2026 at commit `4868801`. That run was blind: nothing in the analyst had been changed in response to it. Fixes followed on 31 October, and the run was scored again at commit `4b952b9`, with new model calls only for the 8 questions whose evidence or route changed.

## Headline numbers

| Metric | Blind run, all | After fixes, all | After fixes, template | After fixes, held-out |
|---|---|---|---|---|
| Integrity (proofs and quotes) | 1.00 | 1.00 | 1.00 | 1.00 |
| Citation precision | 0.999 | 0.998 | 0.999 | 0.992 |
| Citation recall | 0.971 | 0.979 | 0.997 | 0.912 |
| Numeric exactness | 0.913 | 0.938 | 0.971 | 0.727 |
| Refusal F1 | 0.780 | 0.852 | 0.923 | 0.667 |
| Analyst anomaly recall | 0.857 | 0.918 | 1.00 | 0.790 |
| Answer coverage | 0.933 | 0.959 | 0.981 | 0.857 |
| Quote faithfulness | 1.00 | 1.00 | 1.00 | 1.00 |
| Injection resistance | 0.875 | 1.00 | 1.00 | 1.00 |
| Policy section accuracy | 0.588 | 0.588 | 0.545 | 0.667 |
| Reconciliation recall | 1.00 | 1.00 | | |

Two things hold in both runs. No answer cited a record that failed verification, and no quote differed from the regulation's text. Those are guaranteed by construction, and the run confirms it on every answer. Every one of the 206 citations to records outside the labels was a real reconciliation break in the data, not a wrong citation, and they're counted apart.

## The held-out gap

On the blind run, numeric exactness was 0.957 on template questions and 0.636 on held-out ones, a gap of 32 points. After the fixes it's 0.971 and 0.727, a gap of 24. Held-out questions are phrased the way a person would ask, often two questions in one ("Who awarded it, and what was its first modification worth?"), and that's where the system is weakest.

The held-out numbers after the fixes are no longer blind. The fixes are general (they change how lookups, filters, and lists behave for any question), but they were found by reading held-out failures, so the blind run's 0.636 is the honest measure of how the system handles questions it has never seen. A fresh set written by someone else would restore a blind measure; that's listed under what's left.

## By category, after the fixes

| Category | Template | Held-out |
|---|---|---|
| Numeric aggregate | 52 of 53 | 10 of 12 |
| Record lookup | 77 of 80 | 5 of 8 |
| Anomaly list | 10 of 10 | 5 of 7 |
| Policy | 6 of 11 | 4 of 6 |
| Refusal | 18 of 18 | 5 of 5 |
| Injection | 6 of 6 | 1 of 2 |

A question counts here when it's answered (or refused, if it should be), its numbers are exact, it cites what it must, and, for policy, it cites the right section.

## What the blind run found, and what changed

**Lookups that matched more than one record were refused.** A contract number picks out an award and each of its modifications, and a lookup used to answer only when exactly one row matched. Three questions were refused as ambiguous although the records answered them. A lookup now answers with up to 10 matching rows, each cited, and refuses past that.

**A made-up event type gave a confident zero.** Asked to count an agency's de-obligations, the model filtered on an event type called "de-obligation", which doesn't exist, so the count was zero. A filter on a column with a fixed set of values now refuses anything else and names the real values; the model's one repair then sees that a de-obligation is an adjustment with a negative amount. Both such questions are now right.

**A list asked for 1,000 rows was refused.** It now gets the most a list may hold, 100, and says more may match. That question was also one of the two injection questions in the held-out set; it's now answered without following the planted instruction.

**The analyst couldn't be asked about recipient bursts.** The reconciliation rules report them, but no route led there, so the question was refused as out of scope. It now lists the burst breaks.

**Two scoring bugs.** A sum split by group (say, Justice and State side by side) had no single amount, so the scorer had nothing to compare and marked it wrong whatever it said. The same was true of a question asking for a set of distinct values, such as which Treasury accounts paid a contract. The oracle now gives each group's total and the scorer checks each value. These change the score, not the answers.

## What's left, by kind

**Right answer, scored as wrong (6 questions).** The scorer wants every field the oracle lists, and some questions ask for less. "Biggest obligation recorded by the General Services Administration?" is answered with the exact amount, but the expected answer also has the contract number, which the question didn't ask for (F078, F082, F142). The same goes for the agency with the largest total, answered by name without its amount (F055), and for two held-out lookups that leave out the modification number or date (H15, H18). The held-out expectations are frozen and stay as they are; the template ones could be reworded in a later version.

**Policy answers refused as unverifiable (5 questions).** For questions such as "What does the FAR say about change orders in general?" the composer paraphrased instead of quoting, and the verifier refuses a claim about the regulation that isn't a quote (F016, F168, F173, H28, H30). Two more cited a neighbouring section rather than the expected one (F167, F170). That's the right failure for a system that won't make up what a regulation says, but it means policy coverage is the weakest category. Better retrieval of the right section and a composer prompt that asks for a quote first are the next steps; both change prompts, so every recorded response would need to be recorded again.

**Questions the query spec can't express (3 questions).** There's no average metric, so "What's the average obligation per award for Agriculture?" is refused (H11). "How many de-obligations are in the ledger?" was refused as having no data (H05), because the model doesn't connect "de-obligation" with a negative adjustment unless a repair tells it. An anomaly filtered by agency ("Did any Transportation contract pay out more than it obligated?") was routed to a list that can't filter breaks by agency (H27).

**Answers that also show the award itself (2 questions).** Asked when contract SPE60524FVL5B was modified and by how much, the answer gives the right date and amount, but it calls the original award a modification too and leaves out the modification number (H13). Asked to summarize the modifications on Justice contract 15B10624P00000031, it lists the award and its one modification, where the oracle counts one (H40). In both, the query asked for every row of the contract; it should have asked for modifications only.

**Wrong spec (1 question).** For "Find contracts where more has been paid out than was ever obligated" the model listed obligations instead of the reconciliation breaks (H22); the rule that recognises this question by its wording doesn't match "more has been paid out than".

**One refusal with the wrong reason.** A question the data can't answer was refused as out of scope rather than as having no data (H37). It still counts as a correct refusal for recall; it lowers nothing but the reason.

## Speed and cost

The full run used 557,941 tokens, about 2,560 a question, and on the free tier's pacing (4 requests a minute) takes about three nights. Answers replayed from recorded responses take a few milliseconds. In the blind run, the slowest 5 percent of held-out answers took about 45 seconds each, mostly waiting on the provider's rate limit. No question fell back to model-written SQL, and none was too broad to answer.

## Thresholds

The gates were set from the run after the fixes, each at its measured value less about two points. The values are in [evaluation](evaluation.md#thresholds).
