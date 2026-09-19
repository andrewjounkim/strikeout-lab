# Prompt log: Strikeout Lab

## Tools and models actually used

- **Claude Code** (Anthropic's coding assistant, in the VS Code extension) running
  **Claude Sonnet 5** (model ID `claude-sonnet-5`, as reported by the tool's environment).
  It wrote the code, ran the API requests, and ran the tests.
- **Python 3.14**, **Streamlit** (including its built-in `AppTest` headless test
  runner), **requests**, **scipy**, **Plotly**, and **pytest**.
- **Playwright driving Google Chrome** was used by the assistant to open the running
  app, click its controls, and take screenshots. It is not needed to run the app and
  is not in `requirements.txt`.

No other AI tools or models were used for this project.

## Context before this prompt

Earlier in the same session I pasted the assignment brief, then said I was thinking
about a sports betting project, and the assistant built an ESPN odds "line movement
tracker" for it. I decided to scrap that and gave the prompt below instead, so none
of that earlier work is part of Strikeout Lab.

## Prompt 1: the initial prompt (verbatim)

```text
Build “Strikeout Lab,” an interactive MLB pitcher strikeout modeling app for my CMU 15-113 homework, “Explore an API.”

Work with me as a beginner who needs to understand and explain the code. Implement a working app, not just a plan. Make reasonable implementation decisions and keep the scope appropriate for a 5–6 hour student project.

PROJECT CONCEPT

The user chooses a pitcher, an opposing team, and an expected workload. The app estimates a distribution of strikeout totals and the probability of exceeding a user-entered hypothetical strikeout line, such as 5.5.

The interesting question is:
“How do the opponent and the pitcher’s expected workload change the strikeout forecast?”

This is an educational statistical model, not a proven betting system. Do not claim accuracy, profitability, or an advantage over sportsbooks.

TECH STACK

Use:
- Python
- Streamlit for the interface
- requests for API calls
- scipy for probability calculations
- Plotly for interactive charts

Keep the code small, readable, and organized. No database, authentication, paid services, or complicated frontend framework.

FIRST: VERIFY THE API

Use publicly accessible MLB Stats API endpoints under:
https://statsapi.mlb.com/api/v1

Before building the UI:
1. Make actual requests.
2. Inspect the returned JSON.
3. Confirm availability of:
   - MLB teams and pitcher IDs
   - Pitcher season strikeouts and batters faced
   - Opponent team batting strikeouts and plate appearances
   - League batting totals for a league-average strikeout rate
   - Pitcher game logs, if available, for recent starting workloads
4. Record the endpoints, parameters, and fields actually used.

Do not invent fields or assume an endpoint works. If a field is unavailable, simplify the feature and document the limitation. Prefer an API that works without a key. Never silently replace failed API calls with invented statistics.

Use a selectable season. Default to the most recent completed season for a reliable demo, and explain that the selected season supplies the model’s statistics.

CORE MODEL

Use a transparent binomial model.

Calculate:
- pitcher_rate = pitcher strikeouts / pitcher batters faced
- opponent_rate = opponent batting strikeouts / opponent plate appearances
- league_rate = total MLB batting strikeouts / total MLB plate appearances

Compute the league rate from summed counts, not an unweighted average of team percentages. Avoid double-counting aggregate and individual-team totals.

Use a simple matchup adjustment:
p_raw = pitcher_rate * (opponent_rate / league_rate)
p = clamp p_raw to [0.01, 0.60]

This adjustment and its bounds are explicit modeling assumptions, not a fitted or validated formula. If clipping occurs, show a notice.

Let N be the user-selected integer number of batters faced:
K ~ Binomial(N, p)

Calculate:
- Expected strikeouts = N * p
- Probability of each strikeout total from 0 through N
- Probability of going over the selected line
- Probability of going under the selected line
- A central 80% model prediction interval from the distribution

Only allow half-integer strikeout lines, such as 3.5, 4.5, and 5.5, so there are no pushes.
For 5.5, “over” means K >= 6.

Also calculate a pitcher-only baseline using pitcher_rate without the opponent adjustment. Show how much the adjustment changes the expected strikeouts.

Explain that the model assumes a fixed workload and independent plate appearances with a constant strikeout probability. Real games violate these assumptions, so this is a starting model.

WORKLOAD

Let the user adjust batters faced with a slider.

If game logs support it, suggest a default based on the pitcher’s last five starts in the selected season. Filter actual starts, not relief appearances. Show the sample size.

If this cannot be implemented reliably, default to a clearly labeled manual assumption of 24 batters faced. Do not label a manual default as API-derived.

Show a sensitivity chart of the probability of exceeding the line across different workload values. This chart illustrates alternative assumptions, not a confidence interval.

USER EXPERIENCE

Create a polished but simple dashboard:
- Title: Strikeout Lab
- Short plain-language explanation
- Season selector
- Pitcher selector using names, not raw IDs
- Opponent team selector
- Batters-faced slider
- Half-integer strikeout line input

Main results:
- Expected strikeouts
- Probability over the line
- Probability under the line
- Central 80% model prediction interval

Charts:
1. Strikeout probability bar chart, highlighting totals above the line
2. Workload sensitivity chart

Include an expandable “How this model works” section showing:
- Raw API counts
- The three strikeout rates
- The matchup calculation
- The pitcher-only baseline
- Data season and fetch time
- Assumptions and limitations

Use team-level opponent statistics for version one. Do not imply these represent the confirmed lineup.

Do not add sportsbook integration, real bets, player props feeds, injury models, handedness splits, or pitch-level analysis to the initial version.

RELIABILITY

- Cache API responses so slider changes do not make new requests.
- Use request timeouts and clear error messages.
- Handle missing statistics, zero denominators, empty responses, and unavailable seasons.
- Clearly flag small samples.
- Correctly handle pitchers who played for multiple teams: use a verified aggregate or combine raw counts without double-counting.
- If an offline demo is useful, save a small real API response with its source and fetch time. Label offline mode prominently.
- Do not treat baseball innings notation as a decimal; this model should primarily use batters faced.

VALIDATION

Write a few meaningful tests for:
- Probabilities summing to approximately 1
- Correct over/under calculation for half-integer lines
- League-average opponent producing the unadjusted pitcher rate when clipping does not apply
- Missing or zero-denominator inputs

Run the tests and a local startup check. If browser tools are available, inspect the rendered app and exercise its controls.

Do not present historical fitted results as predictive accuracy. Backtesting is optional and should only be added after the core app works. Any backtest must use data available before each evaluated game.

ASSIGNMENT DELIVERABLES

Create:
- Working source code
- requirements.txt
- .gitignore
- README.md
- prompt_log.md

README:
- Project overview
- Installation and exact run command
- A concise 3–5 sentence explanation of API calls, parameters, JSON responses, and authentication
- Model explanation and assumptions
- Data limitations
- A short demo-video outline
- A short description I can adapt for my portfolio

Prompt log:
- Record this initial prompt and important follow-up prompts
- Only name tools/models actually used and known; do not invent a model version

Do not publish, push to GitHub, or deploy automatically.

WORKFLOW

Briefly explain your implementation plan, then begin with a successful API request and build the core app incrementally. Prioritize a complete, understandable version over extra features.

When finished:
1. Tell me exactly how to run it.
2. Summarize what works and any limitations.
3. Explain the API request and probability calculation in beginner-friendly language.
4. List what I still need to do for submission: GitHub upload, portfolio entry, short video, and submission form.
```

### What the assistant did in response, in order

1. **Verified the API before writing any app code**, with real requests to each
   endpoint, and recorded the results in [API_NOTES.md](API_NOTES.md). Findings that
   shaped the design:
   - The league-wide pitcher endpoint returns **one combined row per pitcher**,
     including for pitchers who changed teams. The assistant checked this by adding
     up one traded pitcher's per-team lines (10 + 38 = 48 strikeouts; 111 + 188 = 299
     batters faced), which matched his single row exactly. The per-player endpoint
     returns the combined row *and* the per-team rows, so summing it would
     double-count.
   - Game logs mark starts with `gamesStarted = 1` and reconcile exactly with the
     season line, so the last-five-starts workload default is reliable.
   - Empty or invalid requests return empty data or HTTP 400, never made-up numbers.
2. **Built `model.py` first** (pure math, no network), then `api.py`, then `app.py`,
   testing each against the real API as it went.
3. **Wrote 76 tests**, then deliberately broke the code five ways to confirm the tests
   catch real bugs. (One "surviving" mutation turned out to be a flaw in the
   assistant's own test harness, which had edited a docstring instead of the code;
   redoing it correctly, the tests caught it.)
4. **Ran a startup check and exercised the app** with Streamlit's test runner against
   the live API (confirming slider changes make zero new requests) and in a real
   Chrome browser (slider, selectors, invalid line, expander, offline mode, phone
   width). This found and fixed a legend/title overlap in both charts.
5. **Wrote the README, this log, and the API notes.** Nothing was published, pushed,
   or deployed.

## Follow-up prompts

### Prompt 2: the UI redesign (verbatim)

```text
good work now i just need you to make the ui a lot better and make it easier for people to use like i dont want to go into it seeing a random pitcher line i want a homepage where i can browse and theres a clear mission statement and overall the website is easy to use and navigate. no need for the deploy and subscription/payment feature either
```

**What the assistant did in response:**

1. **Split the single page into four** with a top navigation bar: **Home** (mission statement,
   a three-step guide, top strikeout pitchers), **Browse** (searchable, sortable tables of
   pitchers and teams, click a row to send it to the Lab), **Forecast Lab**, and **How it works**.
2. **Removed the "random pitcher" default.** The Lab now opens empty with a numbered
   step-by-step flow and results appear only after a pitcher and an opponent are chosen. A clearly
   labeled "Just show me an example" button is there for anyone who wants one.
3. **Removed the Deploy button and toolbar menu** through `.streamlit/config.toml`. The app never
   had a subscription or payment feature; the only thing that looked like one was Streamlit's own
   Deploy button, which points to Streamlit's hosting sign-in. That is now hidden.
4. **Kept the original requirements:** the expandable "How this model works" section (with the live
   numbers, data season, fetch times, and assumptions), the labeled manual workload fallback, offline
   mode, and every model behavior.
5. **Rewrote the tests** for the new structure (86 tests) and checked them by mutation, including
   reintroducing the exact "preselected pitcher" problem to confirm a test fails.

**Things the assistant found and fixed along the way** (worth knowing, since they show the process):

- The first version of the rewritten app tests were **not actually offline**: the helper ran the app
  in live mode before switching to offline, so they were quietly calling the real API. The assistant
  noticed when one test failed for an unrelated-looking reason, fixed it by setting offline mode before
  the first run, then re-ran the whole suite with all network access blocked to prove it.
- While checking the running app in Chrome, a button change didn't appear. The cause was a stale test
  server that hadn't reloaded the edited file, not an app bug, so the server was restarted and re-checked.
- Clicking a row after re-sorting the table by column header was tested directly and picks the right
  pitcher.
- On a phone the navigation folds into the `>>` drawer, which is standard Streamlit behavior. This is
  noted in the README.

### Prompts 3 and 4: getting it running

```text
where can i run this to see how it is becfore i tell u its good to go
```

```text
Failed to Load Page
ERR_CONNECTION_REFUSED (-102)
URL: http://localhost:8501/
```

The assistant explained that the app runs locally with `streamlit run app.py`, then, after the
connection error, confirmed nothing was listening on that port (the server wasn't running), verified the
app starts cleanly from a fresh start, and gave the commands and the usual causes (server not started or
stopped, virtual environment not activated, or a different port).

### Prompt 5: use the 2026 season (verbatim)

```text
i need it for 2026
```

This replaced the original instruction (in Prompt 1) to default to the most recent *completed* season.

**What the assistant did in response:**

1. **Checked the 2026 data first.** The 2026 season is still in progress (it ends 2026-09-27), so the assistant
   verified it through the app's own API code before changing anything: 30 teams, about 151 games each, a
   22.1% league strikeout rate, 366 pitchers with a start, and a game log that matches the season line
   exactly. It also confirmed the app already had 2026 in its season list; the real change was the default.
2. **Made the app open on the current season (2026).** The completed seasons are still in the dropdown, and
   the app now labels 2026 as "in progress" on the home banner, in a notice, and in "Top strikeout
   pitchers of 2026 so far", because partial-season numbers change daily.
3. **Added a 2026 offline snapshot** so Offline demo mode matches (it opens on 2026, and 2025 is still
   available). This meant changing the snapshot code from one fixed file to one file per season.
4. **Kept the tests honest:** the existing tests pin exact 2025 numbers, so they now select the 2025 snapshot
   explicitly, and five new tests cover the 2026 default, the in-progress labeling, and snapshot handling
   (91 tests total). Three deliberate reversions (opening on 2025 again, picking the oldest snapshot,
   not flagging 2026 as in progress) were each caught by a test.

### Prompt 6: today's games and the batters (verbatim)

```text
can you also set a section for games that are going on today and pitchers are best to bet on as well as possible over/underperformances based on batters
```

**A deliberate design decision, and why.** The request asks which pitchers are "best to bet on." This model has no
sportsbook lines (the original prompt ruled out sportsbook integration) and has never been tested against real
results, so it cannot say which line is mispriced, and a "best bets" ranking would claim an advantage nobody has shown.
The assistant said so and built the honest version of the same idea: a **Matchup watch** of the pitchers the opposing
bats could **help** (the model expects more strikeouts than the pitcher's own season average) or **hurt** (fewer),
which is the "over/underperformance based on batters" part of the request. The page carries a plain note that these are
model outputs, not bets.

**What the assistant did in response:**

1. **Verified the data first** with real requests: today's schedule with probable pitchers and posted lineups,
   and every batter's season strikeouts and plate appearances. Findings that shaped the design: lineups are posted
   per team and gradually (25 of 30 team-sides that afternoon, 0 of 30 for the next day), games are in mixed states
   (final, in progress, not started), about 84 batter rows are pitchers with no plate appearances, and a traded
   batter's single row equals his two team lines added up, so nothing is double-counted.
2. **Added a Today's Games page.** Each probable starter is modeled against the opposing lineup once it is posted
   (the nine batters' strikeouts and plate appearances added up, not averaged), and against the team's stats otherwise,
   labeled either way. Only games not yet started are ranked. Pitchers with no announced starter or no starts yet are
   listed as not modeled, with the reason. Selecting a row shows the batters behind it, flagging small samples.
3. **Extended the offline snapshot** with batter totals and the saved slate, so the page works offline too.
4. **Tested it** (137 tests): the lineup math and fallbacks, the ranking, game-state handling, parsing of real saved
   schedule and batter responses, and the page itself, including a failed schedule request, an off day, and missing
   batter data. Six deliberate bugs were each caught.

**Things found and fixed along the way:** the first page test found that an offline snapshot with no saved slate
showed a blank page with no explanation (it now says why); an outdated sentence on the About page still claimed the
app defaults to the last completed season (fixed).

### Prompt 7: a better design and a real homepage (verbatim)

```text
can you make the design a bit better like the text font and background make a pretty interactive homepage too that attracks people not just the title
```

**What the assistant did in response:**

1. **Typography and theme.** Chose two open-licensed fonts, Inter for body text and Barlow Condensed for headings and
   big numbers, and bundled them in `static/fonts/` (with their license files) so the app looks the same offline and
   never contacts Google when it runs. They are loaded through Streamlit's own theme settings, so they apply to every
   widget. Added rounded corners, softer colors, and a navy sidebar.
2. **Background and motion.** A soft color wash over a faint dot grid, cards that lift on hover, and fade-in
   animation, all switched off automatically for anyone who has "reduce motion" set.
3. **A homepage that gives people something to do,** built only from real MLB data (nothing decorative is invented):
   an animated banner with a baseball graphic and the mission statement; live stat tiles (league strikeout rate,
   total strikeouts, the strikeout leader, the most strikeout-prone offense); an interactive **"Try it"** widget where
   quick picks and two dropdowns produce a forecast on the spot; a live "on the slate today" card; a chart of the
   strikeout leaders you can flip between pitchers and offenses; and the top strikeout pitchers.
4. **Checked it in a real browser, and fixed what it found:** an overlapping label, a chart label sitting on the bars,
   truncated buttons, a baseball crossing the headline on phones, and a Today table whose last column was clipped
   (the two lists are now stacked). A first attempt at the banner also rendered as plain text because a blank line
   inside HTML ends the block in Markdown, so the markup was flattened.
5. **Tests (151 total):** the homepage tiles, the empty-then-filled "Try it" widget, a test that the homepage widget
   and the Forecast Lab give the **identical** number for the same matchup, the toggle, and the slate card
   (including hiding quietly if the schedule can't load).

### Prompt 8: secrets, and which APIs were used (verbatim)

```text
keep this in mind too for the code Remember, keep API keys and other secrets out of the repo — use environment variables or a local text file or config file excluded from version control. See below for instructions on setting up a .gitignore if needed. (This is only relevant if your API requires authentication or a secret key.)

also tell me what apis were used just so i can explain the project better in video and whatnot
```

**What the assistant did in response:**

1. **Audited the repo for secrets.** The MLB Stats API needs no key, so there was nothing to hide, but a scan of every file
   found no credentials, no credential-looking URL parameters, and only one network host (`statsapi.mlb.com`).
2. **Hardened `.gitignore`** to list `.env`, `.env.*`, `config.local`, `*.local`, and `secrets.toml`, and documented
   the rule (with what to do if a key is ever committed by accident) in the README.
3. **Made it enforceable:** automated tests now fail if a font file is missing, `.gitignore` drops a secrets entry,
   a key, token, or password-like assignment appears in any file, or the code starts calling a second host. Each
   was checked by deliberately breaking it.
4. **Wrote an "APIs used" section** in the README for the video: one data API (the MLB Stats API, six endpoints),
   a note that Python libraries such as `requests` and `streamlit` are tools and not APIs, and that Google Fonts was used
   once at design time to download the fonts and is never called by the running app.

### Prompt 9: a public link (asked as a question)

```text
is it possible to make a public link to it instead of having in the readme and localhost link
```

**What the assistant did in response:** explained that yes, the free route is Streamlit Community Cloud, which needs
the owner to sign in with GitHub (something the assistant cannot do for them). It then prepared the app for a public
server. Thinking about hosting turned up a real bug: a hosted server runs in UTC, so "today's games" would roll over to
tomorrow at about 8 PM Eastern and game times would be shown in UTC without a label. The app now uses Eastern Time
(MLB's own time zone) everywhere and labels times "ET", verified by a test that changes the machine's time zone and
checks the answers don't move. It also rehearsed the deployment: a clean environment built from `requirements.txt`
alone passed all 162 tests, and the app ran correctly with the server clock forced to UTC.

## What I did not do

- No backtest was built. The prompt made it optional, and nothing in the app or docs
  claims predictive accuracy.
- Nothing was committed to git or pushed to GitHub.
