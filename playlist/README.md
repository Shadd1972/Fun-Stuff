# Billboard Monthly #1s by Genre (1985–2010)

This toolkit fetches weekly #1 data from Wikipedia and computes, for each month (Jan 1985 – Dec 2010), the **most popular song** by your rule:
- Winner = song with the **longest run at #1 within that calendar month**.
- Tie-breaker = song with the **longest total run at #1** (across weeks in the year; edges handled by looking at adjacent years when available).
- Output columns: `Year, Month, Song, Artist` (Album intentionally left blank).

It produces **five CSVs**:
- `pop_monthly_1985_2010.csv` (Billboard Hot 100 as proxy for Pop across all years)
- `rock_alt_monthly_1985_2010.csv` (Billboard Alternative/Modern Rock weekly #1s; starts in 1988)
- `rnb_monthly_1985_2010.csv` (Billboard Hot R&B/Hip-Hop Songs / Hot Black Singles)
- `hiphop_monthly_1985_2010.csv` (Billboard Hot Rap Songs; starts in 1989)
- `country_monthly_1985_2010.csv` (Billboard Hot Country Songs)

## Quick Start
1) Ensure you have Python 3.9+.
2) `pip install -r requirements.txt`
3) Run: `python build_monthly_top_by_genre.py`
4) Find the CSVs in the `output/` folder.

## Notes & Limitations
- Wikipedia page structures vary by year and chart. The script tries multiple title patterns and normalizes columns.
- For charts that **start later** (Alt: 1988; Hip-Hop: 1989), earlier months (before the chart existed) will be emitted with blank Song/Artist.
- Tie-break logic:
  - First: weeks at #1 **within the month**.
  - Second: total weeks at #1 **within the year** (the script also loads adjacent year edges to reduce boundary errors).
  - Third (rare): earliest week at #1 **within the month**.

If Wikipedia changes layouts or titles, you may need to tweak the `CANDIDATE_TITLES` patterns inside the script.
