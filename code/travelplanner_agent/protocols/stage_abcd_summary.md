# A/B/C/D research summary

| Stage | Information and mechanism | Delivery | Final Pass | Tokens |
|---|---|---:|---:|---:|
| A | Oracle reference, one Direct planning call | 95.00% | 13.89% | 1,960,945 |
| B | Query-only, autonomous official tools + ReAct | 35.00% | 15.56% | 10,375,639 |
| C | B + one explicit pre-tool Planner | 40.00% | 16.11% | 10,075,583 |
| D | C + one Verifier + at most one no-tool Replan | 41.67% | 16.11% | 11,338,831 |

The experiments support three current conclusions:

1. High delivery with oracle information does not imply high constraint satisfaction:
   A delivers almost every plan but passes only 13.89% end to end.
2. Autonomous information acquisition is the dominant systems challenge. B sharply
   increases cost and loses 60 delivery points relative to A; that is a regime gap,
   not a clean causal effect of tools.
3. Explicit planning provides a small efficiency and delivery benefit (B→C), while the
   tested one-shot Verifier/Replan adds cost without improving overall Final Pass (C→D).

The research chain is therefore not “more components always score higher.” Its useful
finding is a failure-to-mechanism map: global planning modestly reduces waste, whereas a
downstream repair layer cannot recover samples that never produce a candidate and is too
brittle over large raw evidence catalogs.
