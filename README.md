# Job Scout

Job Scout is a personal job-search assistant that goes beyond keyword search. Instead of scrolling through hundreds of listings, you get a ranked list of jobs matched to your actual skills and experience, with a plain-English explanation of *why* each one is a good fit — plus tools to close the gap between where you are and where you want to be.

I built this while running my own job search, because every existing job board answers "what's out there" but not "what's actually right for me, and what am I missing."

## Why this project exists

Job boards are search engines: you type keywords, you get thousands of results, and you're on your own to figure out which ones matter. Job Scout is designed to work more like a research assistant: it reads job postings the way a person would, compares them against your background, and tells you where you stand.

The goal isn't just a bigger list of jobs. It's a smaller, smarter one — with the context to act on it.

## What it does

**Finds relevant jobs, automatically.** Job Scout continuously pulls in fresh job postings and keeps them organized and de-duplicated, so you're always looking at current openings instead of stale or repeated listings.

**Matches jobs to you, not just to a search box.** Rather than relying on exact keyword matches, Job Scout compares the meaning of a job posting to your background and experience, so it can surface strong-fit roles even when the wording is different from your resume.

**Explains its reasoning.** Every match comes with a plain-language explanation of which skills and experience lined up, so you can trust the recommendation instead of wondering why a job showed up.

**Helps you close the gap.** For any role you're interested in, Job Scout can show you what skills or experience tend to separate a strong candidate from a typical applicant, and suggest how to tailor your resume and cover letter for that specific job.

**Tracks your applications.** A simple pipeline view (saved, applied, interviewing, offer) keeps your job search organized in one place instead of a spreadsheet.

**Shows you the market.** Aggregated salary and in-demand-skill trends give a real-time sense of what roles are actually paying and what employers are asking for right now.

## The vision

Long-term, Job Scout is meant to be a career co-pilot, not just a job board: a single place to discover roles, understand where you're competitive, prepare tailored applications, and track the whole process — all grounded in real, current market data rather than generic advice.

## Current status

Job Scout is an active, in-progress project. As of now:

- The data pipeline that continuously collects and organizes job postings is up and running.
- The matching engine that ranks jobs against a candidate profile is in development.
- Career-copilot features (skill-gap analysis, resume tailoring, cover letter drafting) and the application tracker are planned next.
- Market insights (salary and skill trend dashboards) are a later-stage addition.

See `PLAN.md` for the full roadmap and the reasoning behind each technical decision.

## About this project

This project reflects how I approach engineering problems: start from a real need (my own job search), build something that actually works end to end, and make deliberate, defensible choices along the way rather than defaulting to whatever's trendy. It's also a sandbox for the parts of data and ML engineering I care most about — building pipelines that keep data fresh, and turning unstructured text into something a system can reason about and explain.
