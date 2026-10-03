# EOD learning loop
1. After the close `eod_market_opportunities.py` scans the whole NSE equity market for the day's movers and
 `eod_intraday_reconstruction.py` rebuilds their 5-minute setups.
2. `eod_learning.py` finds shares that rose and were not bought, classifies WHY (for example 
SCRAP_WATCH_ONLY,
 EXECUTION_FEATURE_SCORE_BELOW_THRESHOLD, NOT_IN_PAPER_CANDIDATE_UNIVERSE_*) and keeps only reasons seen on
 at least 3 DISTINCT shares in the session.
3. `learning_policy.py` turns those into small steps of GENERAL parameters (1 point per day; universe size 
5):
 SCRAP review cutoff (base 70, floor 60), final review score (base 65, floor 55), shares sent to deep
 analysis (base 60, ceiling 100). Total drift is capped at 15% of the configured base.
4. A net-losing day blocks loosening; a day with a net loss and 2+ stop-losses tightens the two score 
cutoffs.
5. Everything is logged in `data/learning/policy.json` and in `public/data/eod_report.json` (`learning`).
 `LEARNING_ENABLED=0`, or deleting the policy file, restores the configured base values.
6. `paper_cycle.py`, `paper_executor.py`, `scrap_analysis.py` and `market_snapshot.py` read the effective
 values on the next session. Capital, position-size, target and stop limits are never learned.