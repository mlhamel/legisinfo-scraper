# git-rewriting Skill Specification

This skill outlines the implementation details for managing formatting updates and preventing duplicate commits in `legisinfo-scraper` using unique commit identifiers and Git history rewriting.

## 1. Commit Message Identifiers
Every commit created by the scraper must include a machine-readable unique identifier in its commit message body:
* **Sequential Stage Commit**:
  ```
  Bill {bill_number}: {stage_name} text update

  Legisinfo-Event: {session}/{bill_number}/{stage_slug}
  ```
* **Metadata Update Commit**:
  ```
  Bill {bill_number}: Metadata update

  Legisinfo-Event: {session}/{bill_number}/metadata
  ```

---

## 2. Persistent Caching Layer (`--cache-dir`)
To allow re-processing of historical data offline (without hitting Parl.ca servers), we implement a persistent caching layer:
* **CLI Argument**: `--cache-dir` (default: `.cache` in the current working directory).
* **Caching Paths**:
  * Detailed metadata XML: `{cache_dir}/metadata/{session}/{bill_number}.xml`
  * DocumentViewer listing page HTML: `{cache_dir}/docviewer/{session}/{bill_number}.html`
  * Stage XML drafts: `{cache_dir}/stages/{session}/{bill_number}/{slug}.xml`
  * Stage HTML drafts: `{cache_dir}/stages/{session}/{bill_number}/{slug}.html`

---

## 3. Scraper Processing & Force Mode (`--force`)
* Under normal runs, the scraper checks the session index `README.md` to skip already-completed bills.
* With `--force`, the scraper bypasses the skip check and re-processes all bills using local cached files (avoiding network requests).
* For each stage/metadata event, the scraper generates the markdown files.
* If a commit with `Legisinfo-Event: {event_id}` already exists in the Git history:
  1. The scraper compares the newly generated files against the current Git HEAD files.
  2. If they are identical, no action is taken.
  3. If they differ, the scraper stages the changes and creates a Git fixup commit referencing the original commit hash:
     ```bash
     git commit --fixup={commit_hash}
     ```

---

## 4. History Rebase/Autosquash
At the end of a scraper run:
* If any fixup commits were created, the scraper performs a single autosquash rebase using the `GIT_SEQUENCE_EDITOR=true` environment variable to apply all updates to their original commits in a single non-interactive pass:
  ```bash
  GIT_SEQUENCE_EDITOR=true git rebase --interactive --autosquash --root
  ```
