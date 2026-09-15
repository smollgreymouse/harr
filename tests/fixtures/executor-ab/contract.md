# HARR EXECUTOR CONTRACT v1

Goal: update the deterministic A/B fixture from value 41 to value 42.
Success definition: `tests/fixtures/executor-ab/value.txt` contains exactly `value=42` followed by one newline, and the validation command passes.

## Allowed scope
- tests/fixtures/executor-ab/value.txt

## Forbidden changes
- Do not change any other file.
- Do not add files.
- Do not change the validation command.
- Do not commit or push.

## Known facts
- The target file is plain UTF-8 text.
- Its committed initial content is exactly `value=41` followed by one newline.

## Fixed decisions
- This is a literal one-line replacement. No design choice is required.
- Preserve the final trailing newline.

## Step B001
Objective: change the fixture value from 41 to 42.
Target:
- file: tests/fixtures/executor-ab/value.txt
Preconditions:
- the file content is exactly `value=41` followed by one newline.
Exact actions:
1. Replace the complete line `value=41` with `value=42`.
2. Do not modify anything else.
Expected result:
- the file content is exactly `value=42` followed by one newline.
Validation:
- check label: fixture
- command: `python3 -c "from pathlib import Path; assert Path('tests/fixtures/executor-ab/value.txt').read_text(encoding='utf-8') == 'value=42\\n'"`
- expected: exit code 0
STOP if:
- the precondition is false;
- the target file cannot be edited;
- the validation command does not exit 0 after the prescribed edit.

## Final validation
1. Run the validation check `fixture` exactly as specified above.
2. Do not run unrelated tests for this smoke fixture.

## Reporting
- Mark B001 completed only after the exact edit is present.
- Report validation entry with check=`fixture` and status=`PASS` only if the command exits 0.
- Return DONE only after B001 is complete and `fixture` passes.
