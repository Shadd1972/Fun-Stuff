#!/usr/bin/env python3
import re
import os
import sys
import time
import json
import math
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
from dateutil.parser import parse as dateparse

OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)

START_YEAR = 1985
END_YEAR = 2010

# --- Chart configurations ---
# We will use Wikipedia "weekly #1" pages per year.
# Each entry defines candidate page titles (since Wikipedia naming varies).
CHARTS = {
    # Use Hot 100 as proxy for Pop across all years (per user instruction)
    "pop": {
        "start_year": 1985,
        "candidates": [
            # Common pattern
            "List of Billboard Hot 100 number-one singles of {year}",
            "List of Billboard Hot 100 number-ones of {year}",
            "Billboard Hot 100 number-one singles of {year}",
        ],
        "outfile": "pop_monthly_1985_2010.csv"
    },
    # Rock/Alt weekly #1s
    "rock_alt": {
        "start_year": 1988,  # Modern/Alternative Rock begins 1988
        "candidates_by_decade": {
            "1980s": [
                "List of Billboard Alternative Songs number-one singles of the 1980s",
                "Billboard Alternative Songs number-one singles of the 1980s",
            ],
            "1990s": [
                "List of Billboard Alternative Songs number-one singles of the 1990s",
            ],
            "2000s": [
                "List of Billboard Alternative Songs number-one singles of the 2000s",
            ],
        },
        "outfile": "rock_alt_monthly_1985_2010.csv"
    },
    # R&B weekly #1s
    "rnb": {
        "start_year": 1985,
        "candidates": [
            "List of Hot R&B/Hip-Hop Songs number-one singles of {year}",
            "List of Hot Black Singles number-one singles of {year}",
            "Billboard Hot Black Singles number-one singles of {year}",
        ],
        "outfile": "rnb_monthly_1985_2010.csv"
    },
    # Hip-Hop weekly #1s (Rap)
    "hiphop": {
        "start_year": 1989,
        "candidates": [
            "List of Hot Rap Songs number-one singles of {year}",
            "List of Hot Rap Singles number-one singles of {year}",
        ],
        "outfile": "hiphop_monthly_1985_2010.csv"
    },
    # Country weekly #1s
    "country": {
        "start_year": 1985,
        "candidates": [
            "List of Hot Country Singles & Tracks number ones of {year}",
            "List of Hot Country Songs number ones of {year}",
            "List of Hot Country Singles number ones of {year}",
            "List of Billboard Hot Country Songs number-one singles of {year}"
        ],
        "outfile": "country_monthly_1985_2010.csv"
    },
}

WIKI_BASE = "https://en.wikipedia.org/wiki/"

def fetch_wiki_table(url):
    """Try to fetch tables from a Wikipedia page via pandas.read_html."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    # pandas attempts to parse all HTML tables
    tables = pd.read_html(resp.text)
    return tables

def parse_weekly_rows_from_tables(tables):
    """
    Given a list of DataFrames (tables) from a 'weekly #1' wiki page,
    attempt to extract a DataFrame with columns: issue_date, song, artist.
    """
    candidates = []
    for tbl in tables:
        cols = [str(c).strip().lower() for c in tbl.columns]
        # Typical columns: 'issue date', 'song', 'artist(s)'
        if any("issue" in c and "date" in c for c in cols) and any("song" in c for c in cols):
            # Clone to avoid SettingWithCopy issues
            df = tbl.copy()
            # Normalize columns
            rename_map = {}
            for c in df.columns:
                lc = str(c).strip().lower()
                if "issue" in lc and "date" in lc:
                    rename_map[c] = "issue_date"
                elif "song" in lc:
                    rename_map[c] = "song"
                elif "artist" in lc:
                    rename_map[c] = "artist"
            df = df.rename(columns=rename_map)
            if "issue_date" in df.columns and "song" in df.columns:
                # Coerce artist column if absent
                if "artist" not in df.columns:
                    df["artist"] = ""
                # Keep only relevant columns and drop rows with NaN dates/songs
                df = df[["issue_date", "song", "artist"]].dropna(subset=["issue_date", "song"])
                candidates.append(df)
    # Choose the largest plausible table
    if not candidates:
        return None
    best = max(candidates, key=lambda d: len(d))
    return best

def parse_issue_date(val):
    # Try several date formats; Wikipedia uses many
    try:
        return dateparse(str(val), fuzzy=True).date()
    except Exception:
        return None

def compute_monthly_winners(weekly_df, year):
    """
    weekly_df: rows with columns issue_date (datetime.date), song, artist.
    For each calendar month in the given year, choose the song with the
    longest #1 presence in that month. We assume each row represents one week.
    """
    # First, keep only weeks belonging to (year-1, year, year+1) to help edge cases for tie-break
    years_to_keep = {year-1, year, year+1}
    weekly_df = weekly_df.copy()
    weekly_df["y"] = weekly_df["issue_date"].apply(lambda d: d.year if d else None)
    weekly_df = weekly_df[weekly_df["y"].isin(years_to_keep)]
    weekly_df["month"] = weekly_df["issue_date"].apply(lambda d: d.month if d else None)

    # Compute total #1 weeks per song across the captured set (used for tie-break 2)
    total_weeks_per_song = weekly_df.groupby("song").size().to_dict()

    # For each month in target year, count within-month #1s
    rows = []
    for m in range(1, 13):
        month_df = weekly_df[(weekly_df["y"] == year) & (weekly_df["month"] == m)]
        if month_df.empty:
            rows.append({"Year": year, "Month": m, "Song": "", "Artist": ""})
            continue
        # Count within-month weeks per song
        counts = month_df.groupby(["song", "artist"]).size().reset_index(name="weeks_in_month")
        # Add total-year weeks for tie-break
        counts["total_weeks"] = counts["song"].map(total_weeks_per_song).fillna(0).astype(int)
        # Determine earliest appearance in month for final tie-break
        first_week = (
            month_df.groupby(["song", "artist"])["issue_date"]
            .min()
            .reset_index()
            .rename(columns={"issue_date": "first_in_month"})
        )
        counts = counts.merge(first_week, on=["song", "artist"], how="left")
        counts = counts.sort_values(
            by=["weeks_in_month", "total_weeks", "first_in_month"],
            ascending=[False, False, True]
        )
        winner = counts.iloc[0]
        rows.append({
            "Year": year,
            "Month": m,
            "Song": str(winner["song"]).strip(),
            "Artist": str(winner["artist"]).strip()
        })
    return pd.DataFrame(rows)

def get_candidate_urls_for_year(chart_key, year):
    cfg = CHARTS[chart_key]
    urls = []
    # Rock/Alt often uses decade pages listing the entire decade (weekly by date)
    if chart_key == "rock_alt":
        if year < cfg["start_year"]:
            return []
        decade = f"{(year//10)*10}s"  # e.g., 1990s
        title_lists = cfg.get("candidates_by_decade", {}).get(decade, [])
        for t in title_lists:
            urls.append(WIKI_BASE + t)
        return urls

    # Yearly pages pattern
    for t in cfg.get("candidates", []):
        urls.append(WIKI_BASE + t.format(year=year))
    return urls

def load_weekly_df_for_year(chart_key, year):
    """
    Attempt to load a weekly #1 dataframe for a given chart/year.
    For decade pages (rock_alt), we filter rows to the target year.
    """
    urls = get_candidate_urls_for_year(chart_key, year)
    if not urls:
        return None

    for url in urls:
        try:
            tables = fetch_wiki_table(url)
            if not tables: 
                continue
            df = parse_weekly_rows_from_tables(tables)
            if df is None or df.empty:
                continue

            # Parse dates
            df = df.copy()
            df["issue_date"] = df["issue_date"].apply(parse_issue_date)
            df = df.dropna(subset=["issue_date"])

            # For decade pages, filter to the target year
            df["year"] = df["issue_date"].apply(lambda d: d.year)
            if chart_key == "rock_alt":
                df = df[df["year"] == year]
                if df.empty:
                    continue

            # Clean artist column (commas/newlines)
            if "artist" in df.columns:
                df["artist"] = df["artist"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
            else:
                df["artist"] = ""

            # Return if we have something plausible
            if len(df) >= 40 or chart_key == "rock_alt":  # hot 100 ~52 weeks; alt decade pages may still be fine
                return df[["issue_date", "song", "artist"]]
        except Exception as e:
            # Try next candidate
            continue
    return None

def build_chart_csv(chart_key, start_year=START_YEAR, end_year=END_YEAR):
    cfg = CHARTS[chart_key]
    out_path = os.path.join(OUT_DIR, cfg["outfile"])
    all_rows = []
    for y in range(start_year, end_year + 1):
        if y < cfg["start_year"]:
            # Emit blanks for months where the chart didn't exist yet
            for m in range(1, 13):
                all_rows.append({"Year": y, "Month": m, "Song": "", "Artist": ""})
            continue

        # Load the year and also adjacent years for tie-break total weeks
        # We'll build a single DF combining y-1, y, y+1 (if available)
        combined = []
        for yy in [y-1, y, y+1]:
            if yy < cfg["start_year"] or yy < START_YEAR or yy > END_YEAR:
                continue
            df_yy = load_weekly_df_for_year(chart_key, yy)
            if df_yy is not None:
                combined.append(df_yy)
        if not combined:
            # No data found; fill blanks
            for m in range(1, 13):
                all_rows.append({"Year": y, "Month": m, "Song": "", "Artist": ""})
            continue

        weekly = pd.concat(combined, ignore_index=True)
        # Compute monthly winners for the target year
        month_df = compute_monthly_winners(weekly, y)
        all_rows.extend(month_df.to_dict(orient="records"))

    # Finalize CSV
    out = pd.DataFrame(all_rows)
    # Convert Month number -> name
    out["Month"] = out["Month"].apply(lambda m: datetime(2000, int(m), 1).strftime("%B"))
    out = out[["Year", "Month", "Song", "Artist"]]
    out.to_csv(out_path, index=False)
    return out_path

def main():
    results = {}
    for key in ["pop", "rock_alt", "rnb", "hiphop", "country"]:
        print(f"Building {key}...")
        csv_path = build_chart_csv(key, START_YEAR, END_YEAR)
        results[key] = csv_path
        print(f" -> {csv_path}")
        time.sleep(1)  # be gentle to Wikipedia
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
