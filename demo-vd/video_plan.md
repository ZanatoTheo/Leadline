# Leadline demo video plan
Written: 2026-11-15 08:20 EET · Deadline: **10:00 EET** (final submission) · Status: DRAFT, waiting for approval

Built from [research.md](research.md) (full notes in `~/Projects/junction-26-notes/Research/hackathon_demo_videos_market/`),
updated for the current app (Next.js frontend + Leadline service + Venus agent), not the old `app/` prototype.

## The video in one line
Alex, a first-time founder raising a €1.5M seed for Carbonlens, goes from "hundreds of maybes" to a few investors who
really lead rounds like hers, each with sourced reasons, and the same evidence shows up on the investor's side.

## Fixed choices
- **Length: 2:30 target, 3:00 hard cap.** Junction's limit is unknown; most hackathons cap at 3:00. A 2:00 cut drops
  beats 3 and 7 (marked below).
- **Persona = the real demo account.** Alex / Carbonlens (climate, seed, Europe, €1.5M). No invented persona, so
  nothing on screen contradicts the script.
- **The real app on screen for ~2:00 of 2:30.** One slide only (how it works).
- **The memorable thing:** a reason with its source, and the agent saying when it is only guessing
  ("seed-lead fit is inferred rather than direct"). Zoom on it.
- **Say "Cala" out loud** where its data appears (twins, brief). Say "Venus" once, in the how-it-works beat.
- **Honest about data:** no "simulated data" label may appear on screen. If it does, the take is wrong (wrong mode).
- **Leave out:** Signals (0 fund closes in the DB), dark mode, phone layout, signup forms, status page, pricing.

## Script and shots

| # | Time | Screen | Voice (about 150 words a minute) |
|---|---|---|---|
| 1 | 0:00–0:15 | Landing page, then a quick scroll | "Alex is raising a €1.5M seed for Carbonlens. Her investor list has hundreds of names. Most of them never lead a round, and some stopped investing years ago. She can't tell which." |
| 2 | 0:15–0:22 | Log in as demo founder, Today opens | "Leadline shows who actually leads rounds like hers, who is still investing, and why, with a source for every claim." |
| 3 | 0:22–0:35 | Today: the action list *(cut for 2:00)* | "Her day starts here: what changed, and the one thing to do about each." |
| 4 | 0:35–0:58 | Funding twins: similar startups, their rounds, who led | "First, startups that were where Carbonlens is now. Every round, lead and amount comes from Cala's linked data on companies, rounds and investors." |
| 5 | 0:58–1:35 | Who to pitch → open the top investor's brief. **Zoom** on a reason + its source, then on the "inferred" line | "Investors ranked by how they lead, not just who they've met. Open one: it led a round in February, its check covers her raise, and every point has its source. And when the evidence is thin, it says so: this seed-lead fit is inferred, not proven." |
| 6 | 1:35–1:52 | Request intro / outreach email with facts and sources beside it | "One click gives her an intro request or an email that cites the deal, the fit and the source, so the investor can check it." |
| 7 | 1:52–2:10 | Switch to the investor account: Deal flow, an intro request with its fit card, Interested / Pass *(cut for 2:00)* | "The investor sees the same evidence: a fit card with look-alikes from their own portfolio, check size and conflicts. Interested shares contacts. Pass takes one click, and the founder sees why." |
| 8 | 2:10–2:22 | Slide: Cala → Venus agent → ranked leads with sources | "Under the hood, Cala gives the data. Venus, our general agent engine, ranks candidates with a tested strategy and must cite a fact for every reason. Leadline is its first task." |
| 9 | 2:22–2:30 | Back to Who to pitch, then the end card: name, link, repo | "From hundreds of maybes to a few real leads, with proof. Founders use it free; investors pay for sourced deal flow. Leadline." |

## Time budget (EET)
| When | What | Who |
|---|---|---|
| 08:25–08:40 | Start service + frontend, log in to both demo accounts, dry run every click, check for "simulated" labels, pre-load pages | Claude starts the app; user clicks |
| 08:40–08:50 | Make the slide (beat 8) and end card | Claude |
| 08:50–09:10 | Record: screen in one take per beat (1080p, window cropped), then the voice in one take | User |
| 09:10–09:35 | Edit: cut waits (never speed up), add 2 zooms, the slide, the end card | User |
| 09:35–09:45 | Upload (public or unlisted), update `submission.md`, submit | User + Claude |
| 09:45–10:00 | Buffer | |

## Before recording (dry-run checks)
- [ ] App runs from `leadline/data/leadline.db`; no "simulated data" label anywhere
- [ ] Alex's Who to pitch shows ranked investors (only 2 matches today; if thin, pick a seeded founder account with a fuller ranking and rename the persona in the script)
- [ ] The brief shows readable sources, not raw fact IDs like `bidra:f4`
- [ ] The investor demo account has at least one intro request with a fit card (Alex → that fund, made during the dry run)
- [ ] Nothing in the flow triggers a new profile build (that spends Cala calls and waits on the agent)
- [ ] Browser: clean profile, 100–125% zoom, no bookmarks bar, notifications off

## Open (needs the user)
1. Junction's video length limit and the Cala challenge criteria, if known. Each criterion gets a timestamp.
2. Who records: the user's screen recorder (GNOME: Ctrl+Shift+Alt+R, or OBS). Claude can't produce a usable video file.
3. Voice: the user's own voice (recommended), or a clear AI voice.
4. End-card link: the deployed Vercel URL if it's live by 09:30, else the repo only.
5. `submission.md` still describes the old `app/` prototype and must be rewritten before 10:00.
