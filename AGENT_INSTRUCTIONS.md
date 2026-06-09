# Guidelines for AI Coding Agents

> **Scope:** These guidelines govern all AI-assisted edits, feature additions, and refactors in this codebase. Read the entire document before making any changes. When in doubt, prefer the more conservative option and leave a `# TODO(agent):` comment explaining your uncertainty.

---

## Table of Contents

1. [General Agent Behavior](#1-general-agent-behavior)
2. [Strict Type Safety (Python & TypeScript)](#2-strict-type-safety-python--typescript)
3. [Reusable UI Components](#3-reusable-ui-components)
4. [The Scheduler Philosophy](#4-the-scheduler-philosophy)
5. [Source of Truth](#5-source-of-truth)
6. [Error Handling & Resilience](#6-error-handling--resilience)
7. [Testing Requirements](#7-testing-requirements)
8. [Security & Input Validation](#8-security--input-validation)
9. [Performance Guidelines](#9-performance-guidelines)
10. [Code Documentation Standards](#10-code-documentation-standards)
11. [Git & Change Management](#11-git--change-management)
12. [Dependency Management](#12-dependency-management)
13. [.gitignore Management](#13-gitignore-management)

---

## 1. General Agent Behavior

### Think Before You Touch
- **Read before writing.** Always read the relevant files (`models.py`, `scheduler.py`, `templates.json`, component files) before editing any of them. Do not infer structure from filenames alone.
- **Minimal blast radius.** Make the smallest correct change that satisfies the requirement. Avoid refactoring unrelated code in the same commit.
- **No speculative changes.** Do not add "while I'm here" improvements that were not requested. Each change should trace directly to a requirement.

### Clarify Before Proceeding
- If a requirement is ambiguous (e.g., "make the scheduler faster"), stop and ask for clarification rather than guessing intent.
- If two guidelines conflict, flag the conflict explicitly instead of silently picking one.

### Leave the Codebase Better Than You Found It
- Fix any linting errors or type errors you encounter in files you are already touching, even if they are pre-existing.
- Do not introduce new lint warnings or type errors, even in files that already had them.

---

## 2. Strict Type Safety (Python & TypeScript)

### Python

- **All core data structures** must be defined in `models.py` using `@dataclass`. Do not define ad-hoc `dict` shapes inline in `scheduler.py` or anywhere else.
- **Enums or named constants for all categorical data.** Use `str`-based Enums (`class ActivityType(str, Enum)`). For non-categorical magic values (thresholds, limits, buffer sizes), define a named constant at the module level. Never perform raw string comparisons or use unnamed literals in logic.

  ```python
  # BAD
  if activity.type == "FOOD":
      ...

  # GOOD
  if activity.type == ActivityType.FOOD_CONSUMPTION:
      ...
  ```

- **Type annotations are mandatory** on all function signatures: parameters and return types.

  ```python
  # BAD
  def schedule_activity(activity, day):
      ...

  # GOOD
  def schedule_activity(activity: Activity, day: ScheduleDay) -> ScheduleResult:
      ...
  ```

- **Avoid `Any`.** If you find yourself reaching for `Any`, model the type properly in `models.py` instead.
- **Use `Optional[X]` (or `X | None`)** — never bare `None` as a return type without declaring it.
- Run `mypy --strict` before marking any Python task complete. All reported errors must be resolved.

### TypeScript / React

- **Only `.tsx` / `.ts` files.** No `.js` or `.jsx`.
- **`types.ts` mirrors `models.py` exactly.** When you add or modify a Python dataclass, update `types.ts` in the same changeset.
- **Use `import type { ... }`** for all interface/type-only imports in Vite.

  ```typescript
  // BAD
  import { Activity, ScheduleDay } from "./types";

  // GOOD
  import type { Activity, ScheduleDay } from "./types";
  ```

- **No `any`.** Use `unknown` and narrow with type guards when the shape is genuinely unknown (e.g., API responses).
- **Prefer `interface` over `type` alias** for object shapes. Use `type` for unions, intersections, and primitives.
- Run `tsc --noEmit` before marking any TypeScript task complete. Zero errors required.

---

## 3. Reusable UI Components

### No Monoliths

Do not add logic to `App.tsx` beyond routing and top-level state orchestration. If a feature requires more than ~50 lines in `App.tsx`, it belongs in its own component.

### Component Modularity

- Each component lives in its own file and has a single, clearly named responsibility (e.g., `Sidebar.tsx`, `DayCard.tsx`, `ActivityChip.tsx`).
- Props must be **explicitly typed** — never use `any` or spread unknown objects onto components.

  ```typescript
  // BAD
  const DayCard = (props: any) => ...

  // GOOD
  interface DayCardProps {
    day: ScheduleDay;
    onActivityClick: (id: string) => void;
  }
  const DayCard = ({ day, onActivityClick }: DayCardProps) => ...
  ```

- **Avoid prop drilling beyond two levels.** If data needs to travel three or more levels down, introduce a Context or lift state.

### Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Component files | PascalCase | `DayCard.tsx` |
| Hook files | camelCase with `use` prefix | `useScheduler.ts` |
| Utility files | camelCase | `formatTime.ts` |
| CSS modules | Match component name | `DayCard.module.css` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_ACTIVITIES_PER_DAY` |

### State Management Rules

- **Local state first.** Only elevate state to Context or a global store when two or more sibling subtrees need it.
- **No side effects in render.** All data fetching, timers, and subscriptions must live in `useEffect` with proper cleanup.
- **Memoize expensive computations** with `useMemo`; memoize stable callbacks passed to child components with `useCallback`.

---

## 4. The Scheduler Philosophy

### Dynamic, Not Rigid

The `scheduler.py` engine must remain a **dynamic, priority-driven allocator**.

- Do not hardcode specific clock times for low-priority activities (e.g., `hobby_time = "7:00 PM"`). Instead, let the priority-based `check_overlap` logic find open slots.
- All scheduling decisions must be **deterministic** given the same input. Randomness is not permitted.

### Human Constraints Are Inviolable

The scheduler must always enforce:

| Constraint | Rule |
|-----------|------|
| Sleep blocks | Never schedule any activity inside a declared sleep block |
| Work hours | Respect `work_start` / `work_end` from user config |
| Transit buffers | Add `transit_minutes` padding between activities at different physical locations |
| Minimum rest gap | Leave at least `min_gap_minutes` (from config) between consecutive activities |

### Adding New Scheduling Logic

1. Define any new constraint as a flag or numeric field on the `Activity` dataclass in `models.py` (e.g., `energy_cost: int`, `remote_capable: bool`).
2. Add the same field to `templates.json`.
3. Program `scheduler.py` to **react to that flag** — no hardcoded special cases.

Do not add `if activity.name == "Gym":` style logic. The scheduler must not know activity names; it must only know activity properties.

---

## 5. Source of Truth

- `templates.json` is the **sole source of truth** for raw activity definitions. No activity defaults may be defined anywhere else.
- If you find activity data duplicated in Python or TypeScript files, **remove the duplicate and point to `templates.json`**.
- `models.py` is the **sole source of truth** for data shapes. TypeScript types must be derived from it, not invented independently.
- Configuration values (gaps, buffers, work hours) must come from a user config file or environment variables — never from hardcoded literals scattered in business logic.

---

## 6. Error Handling & Resilience

### Python

- Use **specific exception types** — never bare `except:` or `except Exception:` without logging and re-raising or returning a typed error.

  ```python
  # BAD
  try:
      result = schedule(day)
  except:
      return None

  # GOOD
  try:
      result = schedule(day)
  except ScheduleConflictError as e:
      logger.warning("Conflict scheduling %s: %s", day.date, e)
      return ScheduleResult.empty(reason=str(e))
  ```

- Functions that can legitimately fail must return a **typed result object** (e.g., `ScheduleResult`) rather than `None` or raising exceptions as control flow.
- Always validate external input (file I/O, API responses) at the boundary. Never assume a `templates.json` value is present or the correct type.

### TypeScript

- Handle all `Promise` rejections. Do not let unhandled rejections crash the UI.
- API calls must have error states modeled in component state (`isLoading`, `error`, `data`).
- User-facing errors must show a meaningful message — never a raw exception string or a blank screen.

---

## 7. Testing Requirements

### Coverage Expectations

| Layer | Minimum coverage | What to test |
|-------|-----------------|-------------|
| `scheduler.py` | 90% line coverage | Overlap detection, transit buffer logic, edge cases (empty day, fully booked day) |
| `models.py` | 100% | All Enum values, dataclass field defaults |
| React components | Key interactions | Render with props, user click events, error states |
| Utilities / helpers | 100% | Pure functions must be fully tested |

### Rules

- **No test should depend on wall-clock time.** Inject a clock or use a fixed datetime in all scheduler tests.
- **Tests must be deterministic.** Seed any randomness; mock all network calls.
- **One assertion per test concept.** A test named `test_overlap_detection` should not also implicitly test transit buffers.
- Write tests **before or alongside** new features, not after.
- Do not delete existing tests to make CI pass. Fix the underlying code instead.

---

## 8. Security & Input Validation

- **Sanitize all user-supplied input** before it touches the filesystem, database, or scheduler. Reject rather than silently truncate unexpected values.
- **No secrets in source.** API keys, tokens, and credentials must come from environment variables or a secrets manager — never committed to the repo.
- **Validate `templates.json` on load.** Use a schema (e.g., Pydantic model or JSON Schema) to reject malformed activity definitions at startup, not at runtime.
- **Avoid `eval` and `exec`** in Python. Avoid `dangerouslySetInnerHTML` in React unless the content has been explicitly sanitized.
- Keep dependencies up to date. If you add a new dependency, note it in the PR description with a brief justification.

---

## 9. Performance Guidelines

- **Avoid O(n²) scheduling loops.** If iterating over activities and days simultaneously, consider whether the algorithm can be reformulated with a sorted structure or interval tree.
- **Memoize pure Python functions** that are called repeatedly with the same arguments using `functools.lru_cache`.
- **Lazy-load heavy React components** with `React.lazy` + `Suspense` if they are not needed on initial render.
- **Do not block the main thread** in the browser. Any computation taking >50 ms should be moved to a Web Worker or broken into async chunks.
- Profile before optimizing. Add a `# PERF:` comment documenting the benchmark results that motivated an optimization.

---

## 10. Code Documentation Standards

### When to Add Comments

| Situation | Action |
|-----------|--------|
| Non-obvious algorithm or formula | Explain the *why*, not the *what* |
| Magic number or threshold | Explain its origin (e.g., `TRANSIT_BUFFER_MINUTES = 15  # per product spec v2.3`) |
| Known limitation or tech debt | Add `# TODO(agent): <description>` |
| Public API surface | Add a docstring |

### Docstring Format (Python)

```python
def check_overlap(slot: TimeSlot, existing: list[TimeSlot]) -> bool:
    """
    Return True if `slot` overlaps with any slot in `existing`.

    Args:
        slot: The candidate time slot to check.
        existing: Already-scheduled slots for the day.

    Returns:
        True if there is any overlap, False otherwise.
    """
```

### JSDoc Format (TypeScript)

```typescript
/**
 * Formats a duration in minutes as a human-readable string.
 * @param minutes - Duration in whole minutes (non-negative).
 * @returns A string like "1h 30m" or "45m".
 */
export function formatDuration(minutes: number): string { ... }
```

---

## 11. Git & Change Management

- **One logical change per commit.** Do not bundle a bug fix and a feature in the same commit.
- **Commit messages** follow the format: `<type>(<scope>): <short description>` (e.g., `fix(scheduler): prevent double-booking across transit windows`).
- **Never force-push to `main` or `develop`.**
- If a change modifies `templates.json` or `models.py`, the commit message must include `BREAKING CHANGE:` in the body if it alters existing field names or removes fields.
- Add a `# AGENT-MODIFIED:` comment at the top of any file you significantly alter so human reviewers know to inspect it carefully.

### README Update Requirements

The `README.md` is the primary human reference for how this system works. It must stay in sync with the code. **Updating the README is not optional** — it is part of the definition of done for any change that falls into the categories below.

#### When you must update the README

| Change made | Section(s) to update |
|-------------|----------------------|
| New or modified scheduling algorithm (priority logic, overlap detection, slot-finding strategy) | `## How the Scheduler Works` — describe the new algorithm, its inputs, outputs, and any constraints it enforces |
| Changed transit buffer, sleep block, or work-hours enforcement logic | `## Scheduling Constraints` — update the constraint table and any worked examples |
| New or modified data generation script | `## Data Generation` — document the script's purpose, inputs, outputs, flags, and an example invocation |
| New CLI flag or script argument | `## Usage` — add the flag, its type, default value, and a usage example |
| New activity property added to `templates.json` / `models.py` | `## Activity Schema` — document the field name, type, valid values, and how the scheduler reacts to it |
| Change to output file format or structure | `## Output Format` — update the schema description and any sample output shown |
| Removal of a feature or constraint | Strike through or remove the relevant section; add a `> **Removed in vX.Y:**` callout |

#### How to write README updates

The README describes **what the system does now** — not how it got there. It is a snapshot, not a changelog.

- **Current state only.** Rewrite the relevant section to reflect the new behaviour in full. Do not include "previously" or "as of vX.Y" language; that history belongs in the PR description and commit message.
- **One coherent explanation.** A reader should be able to understand the algorithm as a whole concept in a single read, without needing to mentally apply a diff.
- **Keep examples runnable.** Any command or code snippet must work against the current codebase. Remove or replace any example that no longer applies.
- **Plain language.** Avoid jargon or internal shorthand that only makes sense if you've read the source code.

#### Example: README entry after a scheduler algorithm change

```markdown
## How the Scheduler Works

Activities are sorted by `priority` (descending) before slot search begins.
Equal-priority activities are sorted by `duration` (descending) so longer
blocks are placed first, reducing fragmentation.

For each activity, the scheduler scans forward from the start of the day and
assigns the first gap that satisfies all of the following constraints:

1. The slot does not overlap a declared sleep block.
2. The slot falls within work hours for `work_only` activities.
3. A `transit_minutes` buffer separates activities at different locations.
4. The slot respects the configured `min_gap_minutes` between consecutive activities.
```

#### What goes in the PR description instead

The PR description (not the README) is where you record the *reason* for the change. It should include:

- **Why** the old approach was insufficient (e.g., "low-priority activities were crowding out higher-priority ones added later").
- **What changed** and the tradeoffs considered.
- **Before/after comparison** — a short example, table, or sample output showing the difference in behaviour.
- A link to any relevant issue or spec.

---

## 12. Dependency Management

- **Pin all dependencies** to exact versions in `requirements.txt` and `package.json` (`==` in pip, no `^` or `~` in npm).
- Before adding a new library, check whether the existing stdlib (Python) or an already-imported package (React) can solve the problem adequately.
- New Python dependencies must be compatible with the Python version declared in `.python-version` or `pyproject.toml`.
- New npm packages must be audited with `npm audit` before merging. Do not add packages with high-severity vulnerabilities.
- Do not add a dependency solely to use one small utility function — implement it directly unless the library provides substantially more safety or correctness guarantees.

---

## 13. .gitignore Management

### Never Commit These — Ever

The `.gitignore` must cover the following categories at minimum. If any are missing, add them before making other changes.

**Secrets & credentials**
```
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
secrets/
```

**Python artifacts**
```
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.eggs/
.venv/
venv/
env/
*.egg
pip-wheel-metadata/
.mypy_cache/
.pytest_cache/
.coverage
htmlcov/
*.log
```

**Node / frontend artifacts**
```
node_modules/
dist/
.next/
out/
build/
*.tsbuildinfo
.eslintcache
.parcel-cache/
.vite/
```

**Editor & OS noise**
```
.DS_Store
Thumbs.db
.idea/
.vscode/
*.swp
*.swo
*~
```

**Test & coverage output**
```
coverage/
.nyc_output/
test-results/
playwright-report/
```

### Rules for Agents

- **Check `.gitignore` before creating any new file.** If the file type is not already covered, add a rule for it before committing.
- **Never remove an existing `.gitignore` rule** without explicit instruction. A missing rule is a security risk.
- **`.env.example` is the only allowed env file in the repo.** It must contain placeholder values only — no real secrets, tokens, or passwords, even expired ones.
- **Do not use `git add -A` or `git add .`** without first running `git status` to confirm no untracked sensitive files are staged.
- **Generated files belong in `.gitignore`, not the repo.** This includes compiled assets (`dist/`), migration auto-outputs, coverage reports, and type-generation outputs unless they are deliberately vendored.
- **If you generate a new output directory** (e.g., a `reports/` folder from a script), add it to `.gitignore` in the same commit that creates the script.

### Maintaining .gitignore

- Keep `.gitignore` **organised by section** with comments, mirroring the categories above. Do not append rules randomly to the end of the file.
- When a dependency or tool is added (see §12), check its official documentation for recommended `.gitignore` entries and add them.
- Use **global patterns** (`*.log`, `*.pyc`) for file types that should never be committed regardless of location. Use **path-specific patterns** (`/dist/`) only when the rule should apply only at the repo root.

  ```gitignore
  # GOOD — global: ignores .log files anywhere in the tree
  *.log

  # GOOD — path-specific: only ignores /dist/ at the repo root
  /dist/

  # BAD — overly broad and may hide legitimate files
  *
  !src/
  ```

- **Never use negation patterns (`!`) to un-ignore secrets.** If a file is in a secrets category, it stays ignored, no exceptions.

---

## Quick Reference Checklist

Before marking any task complete, verify:

- [ ] `mypy --strict` passes with zero errors
- [ ] `tsc --noEmit` passes with zero errors
- [ ] All new functions have type annotations and docstrings
- [ ] No raw string comparisons — Enums or named constants used throughout
- [ ] `types.ts` updated if `models.py` changed
- [ ] `templates.json` updated if a new activity property was added
- [ ] New logic covered by tests (see coverage table in §7)
- [ ] No secrets or hardcoded magic values committed
- [ ] Commit message follows the `<type>(<scope>): <description>` format
- [ ] No unrelated files modified
- [ ] `README.md` updated if scheduler logic, data generation scripts, CLI flags, activity schema, or output format changed
- [ ] `.gitignore` covers any new file types or output directories introduced
- [ ] No `.env` or secrets files staged (`git status` verified clean)
