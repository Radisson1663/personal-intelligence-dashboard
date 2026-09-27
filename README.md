# Personal Intelligence

A dependency-free, Apple-inspired personal daily-intelligence website.

## Run locally

```sh
python3 app.py
```

Open `http://localhost:8000`. The first launch collects public RSS feeds. It refreshes once per day at 08:00 in `Asia/Shanghai` by default. Set `BRIEF_TIMEZONE` to change the time zone, or press the refresh button to run it immediately.

## What V1 includes

- Real public news sources, curated to the agreed design-led 35/25/20/10/10 category split
- A one-minute brief, design-led top five, 10–15 signals, original-source links, and saved reading list
- A weekly review generated each Monday for the preceding week, and a monthly review generated on the first day of the month for the preceding month
- Automatic in-process daily refresh at 08:00

For a hosted deployment, run this process continuously (or invoke `POST /api/refresh` with a scheduler at 08:00). The saved items and daily brief are stored in `data/brief.json`.
