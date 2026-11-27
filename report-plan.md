# FitApply code review and repair plan

Reviewed FitApply v0.3.0 across the CLI, browser application flow, all seven board integrations, matching, resume parsing and audit, LLM providers, SQLite, both report formats, the test suite, and setup files. Baseline on macOS with Python 3.12.14 was **39 passing tests**, with five PyMuPDF/SWIG deprecation warnings. Both CLI help commands and the offline lockfile consistency check passed. I used synthetic records, temporary databases, and mocks to check failure paths. Live board behavior, account-specific application forms, and provider authentication were outside the verification scope.

## Start here

1. Land **A01** first. The current global dry-run path can click a one-click Apply control and record a submission.
2. Land **A02–A04** before relying on automatic applications. The current flow can act on the wrong page or form, claim success without a receipt, and submit the same job from concurrent runs.
3. Pick up **R01** and **R02** in parallel with browser work. An export can overwrite its source database, and Markdown exports render untrusted content.
4. Use the task index to schedule the remaining fixes. After each task, run its focused tests, then `uv run pytest -v`. When the default uv cache is inaccessible, use `uv run --no-cache --no-sync pytest -v` in an already-synced environment.

Severity measures user impact. **P0** is an unintended external action. **P1** is data loss, privacy exposure, false or duplicate submissions, or a broken core workflow. **P2** is a bounded correctness or maintenance issue. **Reproduced** means a local probe or checked command demonstrated the behavior. **Code trace** means the source shows the path and the task describes a regression test for it.

### Task index

| ID | Priority | Fix | Primary files | Prerequisites |
| --- | --- | --- | --- | --- |
| A01 | P0 | Make dry-run read-only in Chrome | `applier.py`, `cli.py`, README | None |
| A02 | P1 | Scope browser actions to a verified destination and form | `applier.py`, `discovery/iran_boards.py` | A01 |
| A03 | P1 | Verify receipts and preserve uncertainty after a click | `applier.py`, `cli.py` | A02 |
| A04 | P1 | Claim each submission atomically and preserve retryable previews | `store.py`, `cli.py` | A03 |
| A05 | P2 | Contain CDP and page-creation failures | `applier.py` | Land separately from A01–A03 |
| A06 | P1 | Validate model answers and required uploads before sending | `applier.py` | A02 |
| C01 | P1 | Reject unsafe or malformed run configuration early | `cli.py`, `resume.py`, config example | None |
| C02 | P2 | Align status and export database, sorting, and format | `cli.py`, `report.py` | R01 |
| C03 | P2 | Render job and model strings literally in the terminal | `cli.py` | None |
| D01 | P2 | Normalize and deduplicate JobSpy results | `discovery/global_boards.py` | None |
| D02 | P2 | Recover per keyword and per malformed record | Both discovery modules | D01 |
| D03 | P2 | Honor location criteria and verify search contracts | Both discovery modules | D02 |
| M01 | P1 | Restore salary context and settle the unit mismatch | `matcher.py`, `applier.py`, config example | A06 |
| M02 | P1 | Minimize personal data in model requests | `matcher.py`, `applier.py`, README | A06, M01 |
| L01 | P2 | Separate JSON recovery from provider failures | `llm.py` and affected callers | None |
| P01 | P2 | Harden resume cache and validate ATS scores | `resume.py` | None |
| R01 | P1 | Protect the SQLite file from export | `report.py`, `cli.py` | None |
| R02 | P1 | Escape all Markdown fields and validate links | `report.py` | R01 |
| S01 | P1 | Fix first-run instructions and ignore local candidate files | README, `.gitignore`, config example | None |
| T01 | P2 | Make CLI workflow tests hermetic | `tests/test_cli.py` | A04 |

### How to hand a task to a small agent

Production paths below are relative to `src/fitapply/` unless shown with a repository-root path. Line ranges refer to the reviewed tree. Symbol names are the fallback after earlier tasks shift lines. Give the agent one task ID, its listed files and tests, and the relevant prerequisite's status contract. Sequence tasks that edit the same functions. Require a focused regression before the production change and capture the final focused and full-suite results. Keep the current stack, public CLI command names, legacy SQLite rows, and platform IDs compatible. Test with fake browser pages, mocked APIs and LLMs, and temporary files. Mark unresolved live-platform assumptions in the handoff so the next agent can continue without re-reviewing the project.

## Browser actions and application history

### A01 · P0 · Make dry-run read-only in Chrome

**Evidence — reproduced.** `applier.py:194–258` guards the first Apply click only in the effective `site_profile` branch. A synthetic LinkedIn run with `dry_run=True` called `_click_apply_button` once and returned `applied` when the fake page exposed the one-click receipt. Global `auto` and explicit `always_upload` can also reach `set_input_files` before the late dry-run check. Form changes and file selection may trigger page-side requests immediately. The current test exercises only Iranian `auto`.

**Implement.** Make `apply_to_job()` return from a single, read-only dry-run path before any click, fill, select, dynamic-answer call, or file selection. It may inspect the page and report whether an application control or existing application is visible. Say “preview” or “inspect” in CLI help and README where they currently promise form filling. Keep Iranian `auto` on the existing site-hosted resume for live runs.

**Acceptance.** In `tests/test_applier.py`, parameterize Iranian `auto`, Iranian explicit `always_upload`, global `auto` with a PDF, and global `site_profile`. Fake the one-click response and assert both clicks and every form mutation have zero calls. Also cover an existing receipt and a missing control. Run `uv run pytest -q tests/test_applier.py`.

### A02 · P1 · Verify the destination and scope browser actions to the application form

**Evidence — code trace.** `applier.py:176–180, 289–400, 481–509` accepts the posting URL, acts after navigation without checking the final destination, and searches the whole page for substring matches, any textarea, any visible file input, or any form submit. A login, search form, profile form, cookie dialog, or unrelated textarea can receive actions intended for the application. Jobinja also follows hrefs from search results during detail fetches (`discovery/iran_boards.py:79–101, 119–128`).

**Implement.** Require an HTTP(S) posting URL on the configured board host or explicitly supported subdomain. Check the actual page URL after navigation and before sensitive actions. Use exact parsed-host checks, including subdomain boundaries. For Jobinja detail requests, resolve links against its base and validate each redirect hop before following it. Limit live actions to an identifiable posting control and then its identifiable application form or dialog. Remove page-wide mutation fallbacks. A popup, login wall, cross-origin ATS redirect, unknown form, or ambiguous control should yield a manual-action outcome with the posting URL until that flow has a verified adapter. Keep board-specific selector changes backed by fixtures.

**Acceptance.** With browser doubles, verify that legitimate same-board navigation reaches a scoped application action and that a foreign redirect, login form, generic Submit button, and unrelated visible upload field receive no mutation. With an HTTP mock, verify that Jobinja never follows off-board links or redirect hops. Run `uv run pytest -q tests/test_applier.py tests/test_iran_boards.py`.

### A03 · P1 · Record a submission only after verified confirmation

**Evidence — reproduced and code trace.** At `applier.py:261–269`, a mocked final click returned `applied` even though the page exposed no confirmation. One-click and already-applied detection currently search all body text (`183–192, 223–234`), so job copy can masquerade as a receipt. Both click helpers catch broad exceptions and continue to other controls, including when a click may already have fired. `cli.py:394–407` collapses unsuccessful statuses to `failed` and discards failure `notes`.

**Implement.** Select a target before attempting its click. Use an action-specific result, then wait for either an application form or a scoped receipt tied to the current posting. Record `applied` only for confirmed submissions and preserve `already_applied` for an existing verified receipt. Record `submission_unknown` when a click may have fired and the outcome cannot be established. Mark demonstrably pre-submit failures or explicit validation rejections distinctly from ambiguous submissions. Preserve the result and its diagnostic in CLI and SQLite. Once a click may have fired, stop probing other submit controls.

**Acceptance.** Fixtures cover delayed confirmation, explicit rejection, timeout after dispatch, description text containing a confirmation phrase, and an initial click that opens a form. Assert one dispatch per phase, no second click after ambiguity, and matching stored statuses and notes. Run `uv run pytest -q tests/test_applier.py tests/test_cli.py`.

### A04 · P1 · Make previews reusable and concurrent submissions idempotent

**Evidence — reproduced and code trace.** `store.py:63–68, 125–137` treats every non-`discovered` status as permanently evaluated and records `applied_at` for dry runs and failures. A previewed row was both blocked by the existing evaluation gate and assigned an application timestamp. `cli.py:320–323, 381–407` checks, discovers, and calls the browser in separate steps. Two processes can both pass the check. A crash after an external click leaves no durable marker to protect the next run. The two post-browser writes can also disagree if interrupted between commits.

**Implement.** Separate “has a stored evaluation” from “may start a live application.” Allow a live run after `dry_run`; make known pre-submit failures retryable; preserve explicit declines as skipped unless the user deliberately retries them. Keep `applied`, `already_applied`, and `submission_unknown` protected. Before the first potentially submitting action, atomically claim the job in SQLite with a conditional update and commit the claim, then release the transaction before browser I/O. Leave an unresolved claim protected after process death until the board history can establish the result or the user deliberately reconciles it. Persist outcome, notes, and application timestamp together. Preserve protected rows when a preview or another process updates its results. Keep `applied_at` for observed submissions and use a separate field only if an actual attempt timestamp is required.

**Legacy data.** Keep existing `applied` and `already_applied` rows protected. Existing `failed` rows have ambiguous provenance because previous errors could happen after a click. Require reconciliation for those legacy rows instead of bulk retrying them. An existing `dry_run` row may proceed live. Any schema addition must work on a pre-change DB and be safe to re-run.

**Acceptance.** Store tests use two independent connections to the same temp DB and show that only one caller claims a job. CLI tests establish preview → live → terminal, two contenders → one browser dispatch, safe retry after a known pre-submit failure, and interruption → protected claim. Assert preview timestamps stay empty and `applied_today` counts confirmed submissions only. Run `uv run pytest -q tests/test_store.py tests/test_cli.py`.

### A05 · P2 · Contain CDP and page-creation failures

**Evidence — reproduced and code trace.** `applier.py:123–129, 161–178, 278–287` creates the page before the guarded block. A fake `new_page()` error escaped and owned Playwright was stopped zero times. The configured timeout is used for navigation, but not for `connect_over_cdp()`; click calls also use Playwright defaults, and `is_visible(timeout=...)` is used as if it waits for the control.

**Implement.** Enter cleanup coverage before page creation, track an optional page, and stop per-call Playwright on normal failure and cancellation. Preserve batch-owned Playwright cleanup in the context manager. Return a per-job pre-submit failure on page creation. Pass the configured CDP timeout explicitly and use bounded waits for dynamic conditions where needed, especially in the receipt path from A03.

**Acceptance.** Mock connection refusal, `new_page()` failure, page cleanup failure, and a disconnected managed browser. Verify owned instances stop once, managed connections reconnect when stale, and connection timeout is forwarded. Run `uv run pytest -q tests/test_applier.py`.

### A06 · P1 · Validate screening answers and required uploads before submitting

**Evidence — code trace.** `applier.py:236–262, 387–479` silently swallows upload and screening errors and proceeds to Submit. `always_upload` also proceeds without a PDF. Screening scans page-wide inputs, proposes answers for model-supplied keys outside the original list, includes select defaults, and can overwrite existing answers. A generated answer can target an unrelated field or invent an answer the candidate did not provide.

**Implement.** Use A02's scoped form. Snapshot eligible, visible, enabled, empty application controls, give each an opaque local identifier, and apply only answers for those identifiers. Recheck eligibility before filling. Resolve selections against known available choices and leave sensitive declarations or unsupported field types for manual review. Keep prefilled values. For live `always_upload`, require a readable PDF before browser I/O and block submission when a required upload fails or the resume control cannot be verified. In global `auto`, allow a form without a required upload; block a known required upload that could not be satisfied. Never inspect or write to file inputs in `site_profile`. Surface unresolved required answers and validation errors as actionable manual outcomes.

**Acceptance.** Mock an unknown model key, a prefilled select, unsupported controls, invalid choices, and missing or rejected uploads. Assert no mutation outside the eligible controls and no final click for incomplete required inputs. Verify an optional missing upload permits a valid `auto` form. Run `uv run pytest -q tests/test_applier.py tests/test_cli.py`.

## CLI and configuration

### C01 · P1 · Validate configuration before matching or submission

**Evidence — reproduced and code trace.** `cli.py:42–53, 212–268, 287–306` silently falls back when an explicit `--config` file is missing. A CLI probe fell through to a local YAML file with a null upload mode and raised `AttributeError`. YAML can also return a list or scalar, strings can pass into list loops, and numeric bounds are unchecked. Selecting only unknown sites exits successfully after setup. `resume.py:77–107` can substitute search keywords as skills, three years of experience, and two languages. `config.example.yaml:15–33, 68–80` contains sample candidate facts and contact details plus a plausible phone number. These paths can supply invented facts to matching or applications. A configured but missing PDF falls back silently, even when the chosen upload mode requires it.

**Implement.** Require an explicit config path to exist and report file, YAML, and shape errors through predictable CLI exits. Validate relevant mappings and field types before starting browser or LLM work. Enforce score `0..100`, a positive application limit and timeout, and at least one recognized platform. Keep the mixed known/unknown warning. Keep explicit PDF errors clear and report when a configured optional PDF is absent. Require real candidate profile facts or a readable PDF before live applications, even in interactive mode. Replace fabricated fallback skills, years, and languages with unknown/empty values and stop samples from passing as live candidate data. For path references, document and test how relative paths in an explicitly selected config file resolve.

**Acceptance.** Use `CliRunner` and isolated files for missing explicit YAML, malformed/root scalar YAML, null settings, string list values, invalid numbers, all-unknown sites, and an unconfigured live run. Assert failures occur before provider creation, browser calls, or DB writes. Verify an explicit site-hosted candidate with zero years remains valid. Update the existing tests that currently depend on an unknown platform returning success. Run `uv run pytest -q tests/test_cli.py tests/test_resume.py`.

### C02 · P2 · Make status and export agree

**Evidence — code trace.** `run` uses `cfg["db_path"]` (`cli.py:283`), but `status` silently opens the default unless passed `--db` (`125–136`). The table honors `--sort` and export hardcodes fit score (`cli.py:149–185`, `report.py:340–369`). `--html --export output.md` silently produces Markdown and opens nothing. Top-level HTML metrics label all rows “Total Jobs Evaluated,” including discovered rows, while CLI counts tracked jobs.

**Implement.** Let `status` use the same configured path and preserve explicit `--db` precedence. Forward validated sort, filter and limit to export with a backward-compatible default. Decide and document a clear error for `--html` with a non-HTML output path. Use the actual tracked count in the HTML label. Make clear that the Markdown detail cutoff of 75 is a report convention if it remains independent of the run threshold. Keep standalone HTML output.

**Acceptance.** Two temp DBs with opposing timestamps and scores prove the DB override and ordering. Check empty and nonempty exports, invalid sort/limit/format handling, and a mocked browser open for `--html`. Run `uv run pytest -q tests/test_cli.py tests/test_report.py`.

### C03 · P2 · Treat terminal data as literal text

**Evidence — reproduced at the renderer.** A synthetic Rich string containing an unmatched closing tag raised `MarkupError`. `cli.py:66–119, 164–173, 235–276, 325–369` interpolates provider, job, config, and error strings directly into Rich markup, including progress messages and prompts. Untrusted brackets can change styles or crash the CLI after evaluation. Export escaping from R02 does not cover terminal output.

**Implement.** Use literal Rich `Text` or escape each interpolated value with `rich.markup.escape` before handing it to any markup renderer. Keep application questions and presentation markup readable.

**Acceptance.** Use a synthetic job with bracket-like text and a provider verdict containing a mismatched closing tag. Run through the matching card, confirmation or dry-run, and status views, and verify literal output with no `MarkupError`. Run `uv run pytest -q tests/test_cli.py`.

## Discovery and matching

### D01 · P2 · Normalize and deduplicate global JobSpy results

**Evidence — reproduced and code trace.** `discovery/global_boards.py:46–98` has no per-search `seen_ids`. A stubbed two-keyword search returned each ID twice and rendered a missing description as `"nan"`. Duplicates can consume the connector limit before CLI deduplication. Pandas missing values can also raise during truth testing, losing later rows because the keyword loop catches the error outside the row loop. The adapter leaves `JobPosting.salary` unset even if a JobSpy row supplies compensation.

**Implement.** Normalize scalar missing values explicitly before string conversion. Skip rows without usable URLs; let missing text fall back to meaningful defaults. Keep known stable IDs for old DBs, add per-search deduplication after a row validates, and ensure unique rows determine the limit. Treat one bad row as a local omission. Extract salary only from verified JobSpy fields, retaining source currency and interval, or leave it unknown. Inspect the installed package's mapping before selecting fixture columns.

**Acceptance.** Stub `jobspy.scrape_jobs` and use rows with duplicate IDs across queries, missing ID plus URL fallback, NaN text, nullable scalar URL, and a valid row after the bad one. Verify stable IDs, expected salary if fixture fields support it, and unique limits. Run `uv run pytest -q tests/test_discovery.py tests/test_remotive_themuse.py`.

### D02 · P2 · Fix keyword fallback and isolate malformed listings

**Evidence — reproduced and code trace.** In Jobvision (`discovery/iran_boards.py:160–218`), `if results: continue` uses cumulative results. In a two-keyword probe, the second response was empty and no fallback GET occurred. `data: null` prevents the alternate `items` lookup. Jobvision, Remotive, and The Muse can abandon an entire keyword when one row has an unexpected shape, and their IDs are consumed before successful model construction. Remotive and The Muse use a tag-stripping regex that leaves entity references such as `&amp;` in matching text. `_extract_post_id()` at `iran_boards.py:27–33` returned `#info` for a URL ending in `/1/#info`.

**Implement.** Scope fallback selection to validated results for the current keyword. Normalize the accepted response container shapes, validate individual records, and only add IDs after a posting is built. Derive Iranian IDs from the parsed URL path so query strings and fragments never enter the ID. Keep normal historical IDs stable. Ignore obvious index/navigation links in fallback results. Decode entities with the existing HTML parser when normalizing remote descriptions.

**Acceptance.** Mock first keyword API success then second keyword API empty with a valid fallback card. Also test null wrapper plus alternate collection, malformed row before a valid one, bad first duplicate followed by valid data, fragment/trailing slash/query equivalence, and entity decoding. Run `uv run pytest -q tests/test_iran_boards.py tests/test_remotive_themuse.py`.

### D03 · P2 · Make search criteria work consistently

**Evidence — code trace.** Iranian boards, Remotive, and The Muse accept but never use `locations`. JobSpy uses only `locations[0]` (`global_boards.py:47–62`), so the example `["Tehran", "Remote"]` searches just Tehran there. The Muse requests page zero for every keyword with a `query` parameter. The mocked response is independent of that parameter, so tests establish parsing only. The Muse also labels absent location metadata as “Remote / Flexible,” which conflates missing data and verified remote jobs. Matcher receives the job location but no list of configured target locations.

**Implement.** Consume all configured JobSpy locations within a bounded query budget. For other boards, use documented location filters where supported and a small local filter over known location metadata where meaningful. Keep unknown locations visibly unknown. Preserve country restrictions in remote results. For The Muse, check the upstream API contract before choosing search parameters. If free-text search is unavailable, use bounded pagination and local keyword matching rather than implying server-side filtering. Pass relevant location preferences to matching so discovery and scoring consume the same inputs.

**Acceptance.** Mock a result found only at the second location, a remote posting restricted to a country, a posting with unknown location, and a The Muse fixture that ignores unknown query parameters. Verify deterministic limits and no duplicate IDs across location or page boundaries. Run `uv run pytest -q tests/test_discovery.py tests/test_iran_boards.py tests/test_remotive_themuse.py tests/test_matcher.py`.

### M01 · P1 · Supply actual salary and resolve currency/period ambiguity

**Evidence — reproduced and code trace.** The matching prompt asks for compensation fit but omits `job.salary` (`matcher.py:59–85`). A capture confirmed an available USD salary was absent. The example key `salary_expectation_irr_monthly` has value `60000000` with a comment claiming 60 million tomans / 600 million rials (`config.example.yaml:75`). `applier.py:368–385` places the raw number in the first salary-like field, regardless of currency or pay period. A field can therefore receive a tenfold error or an amount denominated in the wrong currency. The current default `compensation_fit="acceptable"` is outside the categories advertised by the prompt.

**Implement.** Include offered salary, its source units and period when known, and the configured candidate salary units in the prompt. Represent missing salary as unspecified and do not imply parity across currencies or periods. Choose an unambiguous documented example value in rials. Preserve existing configurations as rials and avoid guessing whether they were entered in tomans. Fill salary fields only when the expected currency and period are explicit or verified by a board-specific adapter. Convert rials to tomans only for an explicitly toman-denominated monthly field. Leave ambiguous fields for review under A06.

**Acceptance.** A captured prompt contains source salary and expectation with their units. Fixtures distinguish monthly rials, monthly tomans, unrelated annual currency, and an unlabeled amount. Verify only the first two receive the expected value and missing compensation stays unspecified. Run `uv run pytest -q tests/test_matcher.py tests/test_applier.py`.

### M02 · P1 · Reduce candidate disclosure to model providers

**Evidence — reproduced and code trace.** `matcher.py:44–76` sends every truthy `candidate_answers` field alongside the candidate name. A synthetic contact marker appeared in the prompt. `applier.py:433–444` sends the full profile and extra details when any question is found. This can disclose email, phone, and military service to a configured provider even when matching or screening does not need them. Job descriptions and form labels are external text mixed into prompts, and the generated cover letter can go straight to a site. This is a data-flow finding; the review made no external provider calls.

**Implement.** Build explicit match inputs from professional qualifications, location preference, and compensation fields. Fill exact known contact fields locally from user configuration when appropriate. Give the screening provider only the facts relevant to eligible unresolved questions. Treat job text and field labels as data in the prompt and retain A06's enforcement in code. Keep only operator-approved profile facts available for outgoing messages. Document the provider data flow for resume parsing and audits, where the currently bounded raw PDF text is sent by design.

**Acceptance.** Spy prompts contain skills and compensation, exclude synthetic email/phone/service markers where irrelevant, and omit the full profile on a single screening question. Verify a known contact field uses local data. Run `uv run pytest -q tests/test_matcher.py tests/test_applier.py tests/test_resume.py tests/test_audit.py`.

## Providers and resume

### L01 · P2 · Separate malformed JSON from provider errors

**Evidence — reproduced.** A provider stub raising `RuntimeError` was called twice by `BaseLLM.complete_structured()` (`llm.py:51–65`). The catch-all treats provider failures like parse failures and pastes exception details into logs and the retry prompt. Pydantic validation errors may render raw model values. Evaluation or cache logs can then retain additional copies of candidate data.

**Implement.** Call the provider outside the parse/validation exception handler. Keep one corrective retry for malformed JSON or schema validation errors only. Use a generic corrective message and sanitized error categories, and keep the final CLI/store diagnostic actionable without persisting raw responses or provider exception bodies. Preserve existing fenced JSON support.

**Acceptance.** A fake provider error is called once and classified correctly, malformed JSON retries once successfully, invalid schema follows the same path, and a synthetic sensitive value never appears in captured logs or the corrective prompt. Run `uv run pytest -q tests/test_llm.py tests/test_cli.py`.

### P01 · P2 · Harden PDF/cache handling and bound the ATS score

**Evidence — code trace and reproduced.** `resume.py:65–74` opens a PDF without explicit cleanup; the extraction loops through all pages before truncating the LLM payload. `119–158` trusts cache-file mtime and writes cache JSON directly. Replacement PDFs with equal/older timestamps can reuse stale results, and interrupted writes can lose a valid cache. The cache contains contact information and inherits ambient file permissions. `ResumeAuditResult` accepted an ATS score of 101; its Field description advertises 0–100 but imposes no bounds.

**Implement.** Use a context manager for the PDF and enforce the existing 15,000-character prompt budget during collection on parse/audit paths, preserving the public full extraction helper. Write the sidecar atomically with owner-only permissions where supported. Tie new cache entries to a source fingerprint that catches same-mtime content replacement. Handle legacy cache entries explicitly, either by revalidating or treating them as stale once and rebuilding, and keep corrupt/unwritable cache nonfatal. Enforce `ats_score` range in the response model so structured recovery can correct it.

**Acceptance.** Tests cover same-mtime PDF replacement, unchanged PDF cache hit without an LLM call, corrupt and unwritable cache, interrupted writes preserving the old file, prompt bound, and ATS values at 0, 100, and outside the range. Run `uv run pytest -q tests/test_resume.py tests/test_pdf_integration.py tests/test_audit.py`.

## Reports and setup

### R01 · P1 · Protect SQLite from an export write

**Evidence — reproduced.** `report.py:349–366` reads the DB then writes to any supplied path, so `export_report(db, db)` replaced a temporary SQLite file with Markdown. `status --db path --export path` reaches the same function. Symlinks and hard links can alias the database even when the input strings differ.

**Implement.** Resolve and check the export target before any writes. Reject the source DB and SQLite sidecar paths, including aliases to existing files. Use a same-directory temporary file and atomic replacement for a normal report write, and expose a clear CLI diagnostic for a refused target. Preserve UTF-8 and the existing export formats.

**Acceptance.** Test identical path, relative alias, symlink/hard-link alias where supported, and sidecar destination. Verify the temporary DB stays queryable in every case and a normal existing report can be refreshed. Run `uv run pytest -q tests/test_report.py tests/test_cli.py`.

### R02 · P1 · Escape Markdown by context and validate exported links

**Evidence — reproduced.** `report.py:31–73` only changes table-cell pipes and line breaks for a subset of fields. A local probe found raw HTML and a file-scheme link in the Markdown output. The detail section interpolates titles, reasons and notes directly, and the fixed-length cover-letter fence can be closed by the content. HTML has attribute/text escaping and a scheme prefix check, but accepts URL text without a parsed host (`report.py:119–134`). The existing sanitization test only rejects dangerous URL schemes in HTML.

**Implement.** Share a validated HTTP(S) URL routine across both exports. Require a parsed hostname, reject control characters and malformed links, and escape or encode destinations for each format. Emit plain text or omit the link for invalid URLs. Escape Markdown separately for table cells, headings, list fields, and cover notes. Escape embedded HTML, line structure, and backticks as appropriate. For multiline cover notes, use indented code or a fence longer than any run in the data. Keep the dashboard standalone.

**Acceptance.** Add context-specific tests with pipes, markdown links, angle brackets, multiline strings, and backticks. Verify non-web and malformed URLs become nonlinks in both formats and that valid HTTPS URLs with query parameters are usable. Keep existing HTML escape assertions and replace the Markdown assertion that expects raw markup. Run `uv run pytest -q tests/test_report.py`.

### S01 · P1 · Make first-run setup reproducible and keep local candidate files out of Git

**Evidence — reproduced and code trace.** `README.md:13–25` uses plain `uv sync` before `audit`. The default provider is Antigravity in the example and factory, but `pyproject.toml:21–28` makes its SDK and pytest optional. The current environment had no importable `google.antigravity`. `git check-ignore` confirmed `config.yaml`, `resume.pdf`, and the standard report names are not ignored. The README directs users to copy the sample into `config.yaml`, which can contain contact details. The config comment also promises daily rate limiting when the CLI only caps each run.

**Implement.** Give users a working provider setup path, including the extra or a configured LiteLLM model and credentials. Document `uv sync --extra dev` for tests alongside the chosen provider setup. Make the missing-SDK error point to the supported extra. Ignore standard local private paths for config, resume and generated reports while keeping samples and this repair plan trackable. Describe the limit as per-run. Preserve version alignment across README, pyproject and package.

**Acceptance.** Check the default config instructions against dependency metadata and mock missing/provider-present imports. Verify `git check-ignore` matches private defaults while examples and `report-plan.md` remain trackable. Check the lockfile if dependency metadata changes and run `uv run pytest -q tests/test_llm.py tests/test_cli.py`.

### T01 · P2 · Test the real CLI orchestration without external I/O

**Evidence — code trace.** `tests/test_cli.py:52–122` runs an unknown site for both integration tests. The first creates an unused temporary DB path. Both can initialize the workspace default `data/jobs.db` and rely on repository config while skipping worker behavior. `test_iran_boards.py` mocks POST but does not stub GET on the path where a parsing regression triggers fallback.

**Implement.** Run the CLI tests inside an isolated working directory with an explicit temp config and DB. Inject one discoverer, one deterministic fake provider, and a fake applier through the normal CLI flow. Consolidate workflow cases that A01–A04 already add. Stub both HTTP verbs in discovery fixtures that exercise fallback. Replace fixed test sleep with a scoped async stub.

**Acceptance.** Assert provider, discoverer, and applier calls in a successful fake workflow and inspect the resulting temp DB. Fail if the workflow attempts network, real CDP, or any write outside the test directory. Run `uv run pytest -q tests/test_cli.py tests/test_iran_boards.py`.

## Integration checks after the repairs

- Run `uv run pytest -v` and both CLI help commands, `uv run fitapply --help` and `uv run fitapply run --help`.
- With fixture pages, exercise site-hosted Iranian preview, global preview with a PDF supplied, a verified one-click receipt, a verified form receipt, an employer validation error, a destination change, and an ambiguous submission. Count mutating browser calls and check stored status after each.
- With an older temp DB, verify live after preview, refusal to re-enter a protected application, one claim for two processes, and reporting on legacy rows. Export both Markdown and standalone HTML with the same filters and order.
- Keep live board selectors, login flow, and API parameter verification separate from the offline suite. Use captured non-sensitive fixtures to document each supported flow before re-enabling automation where the application boundary is uncertain.
