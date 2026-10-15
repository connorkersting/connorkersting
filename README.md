<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/portrait-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/portrait-light.svg">
  <img alt="Animated ASCII portrait of Connor Kersting next to a terminal card: MSBAi '27 at UT Knoxville, focused on analytics engineering and AI solutions." src="assets/portrait-dark.svg" width="100%">
</picture>

I'm Connor, an MSBAi student at UT Knoxville's Haslam College of Business graduating in May 2027, and I'm looking for analytics engineer and AI solutions engineer roles. I like building the pipeline first and the analysis on top of it. When the answer comes back null, I report the null.

### Featured work

**[MOONSHOT](https://github.com/connorkersting/moonshot)** · Claude Code agent loop, Python, ffmpeg, dbt, DuckDB<br>
A Claude Code loop spent 24 hours cutting an 87.5-second Apollo 11 trailer from NASA public-domain footage, through 28 versions. Critics that hadn't built a version judged each one, and a blind A/B test plus an editor critic decided what stayed. The more useful finding came after the run. Asked to re-score the same 8 versions three times, the editor critic agreed with itself at an ICC of 0.38, well short of the 0.75 set in advance, so a half-point gain between versions is within noise. The agent wrote all the code, including the dbt warehouse that measures the run. I directed: I set the budget and the stopping rule, approved the tools, caught two audio defects by ear and made the picture calls.

**[US Housing: Buy vs. Rent](https://github.com/connorkersting/us-housing-buy-vs-rent)** · [live app](https://connorkersting.shinyapps.io/us-housing-buy-vs-rent/) · R, Shiny, Zillow Research data<br>
Change the down payment and the kind of rental you compare against, and the number of US metros where buying costs less per month than renting moves from 0 to 89 (out of 382 to 389, depending on the rent series). Even in the 89 that flip at 20% down, the median household needs 6.4 years to save the down payment. It was a team project for a storytelling course. I did the data work: the prep script over 8 raw Zillow CSVs, every number the app shows, and the method choices. Claude wrote the app skeleton and much of the chart code; the repo's AI log lists which parts.

**[fantasy-warehouse](https://github.com/connorkersting/fantasy-warehouse)** · dbt, DuckDB<br>
A tested dbt layer over my scheduled fantasy-football pipeline: a pinned source contract that fails loudly on schema drift, a declared grain on every model, and row counts reconciled on every run. The headline is a negative result. Across 13 replayed decisions the tool's recommended lineup never beat the platform's default (11 ties, 2 losses). The agent wrote the SQL; I set the two questions and the rules it had to enforce.

**[Local LLMs vs a paid API](https://github.com/connorkersting/local-llm-sentiment-eval)** · Ollama, Python<br>
Can a laptop model replace a cloud API for bulk labelling? On 300 financial-news sentences, qwen3.5:9b scored 93.0% at 280 items a minute on an 8 GB laptop GPU. Always guessing "neutral" scores 63%. Claude Haiku 5.5 scored 90.3% with thinking off and 93.7% with it on, so the local model matched the paid one at no per-item cost. Turning thinking off made gemma4 9x faster and 9 points more accurate.

**[Rocky Top Outfitters data pipeline](https://github.com/AkyuzBurhan/rocky-top-data-pipeline)** · team of 4 · Python, SQLite, GitHub Actions, Streamlit<br>
A GitHub Action loaded 99 daily order files between July 7 and October 15, 2026. Burhan built the core pipeline; my part was the analysis, verification and docs. On rainy days pickup share rose from 17.9% to 21.6% (z = 2.76) across 3,721 order lines, while the revenue effect was null, and we reported it as null. I also re-ran the current quality gate over every historical raw file and ran the poison-fixture demo, where a deliberately bad file has to trip the gate.

### This profile is a pipeline

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/live-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/live-light.svg">
  <img alt="Dot chart of price-to-rent ratios for the 20 largest US metros, this year versus last, from Zillow Research data." src="assets/live-dark.svg" width="100%">
</picture>

[![live data](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fconnorkersting%2Fconnorkersting%2Fmain%2Fdata%2Fbadge.json)](https://github.com/connorkersting/connorkersting/actions/workflows/refresh.yml)

A GitHub Action is scheduled to rebuild the chart above on the 20th of every month. A GitHub Action pulls Zillow's home-value and rent indexes, checks both files against a pinned schema, and reconciles metro counts across the join. If any check fails, the run stops without committing and the last good chart stays up. The code is in [pipeline/](pipeline/), with tests in [tests/](tests/).

### How I work

AI coding agents (Claude Code and Codex) write most of my code, this profile's pipeline included. I write the spec, decide which checks the output has to pass, and verify the result against numbers I can reproduce: tests, row-count reconciliation, and a read of the output myself before anything ships. The README in each of my repos says which parts were mine.

[LinkedIn](https://www.linkedin.com/in/connorkersting)
