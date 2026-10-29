# runreceipt

Keep a receipt for a Python command, then compare it with the next run.

When yesterday's script worked and today's fails, the command alone is rarely enough to explain the difference. runreceipt records the interpreter, installed package versions, selected file hashes, selected environment fingerprints and exit status. The comparison gives you a short list of changes to investigate.

It also hashes selected files after the command finishes, so an input that the program overwrote does not silently look like the input it started with.

## Install

Requires Python 3.10 or newer. There are no runtime package dependencies. Git is optional; when available, the receipt includes the commit and whether tracked files were dirty.

```sh
python -m pip install 'git+https://github.com/Vansh-738/runreceipt.git@v0.1.0'
```

A wheel and source archive are available in [Releases](https://github.com/Vansh-738/runreceipt/releases).

## Record a run

```sh
runreceipt run --track src --track settings.toml --env MODEL_NAME -- train.py
```

The arguments after `--` go to Python. The command inherits stdin, stdout and stderr, runs in the project directory, and keeps its normal output. The receipt summary goes to stderr. Shell syntax is not interpreted.

To run a module:

```sh
runreceipt run --track src -- -m pytest tests/
```

To inspect and run a different virtual environment:

```sh
runreceipt run --python .venv/bin/python --track src -- job.py
```

On Windows, use `.venv\Scripts\python.exe`. Without `--python`, the interpreter running runreceipt is used. Install the tool in the environment you want to record, or select that environment explicitly.

Each receipt is saved under `.runreceipt/runs/` with a 12-character ID. Add `.runreceipt/` to your project's `.gitignore`; runreceipt does not edit it for you.

## Compare runs

```sh
runreceipt list
runreceipt diff WORKING_ID FAILING_ID
runreceipt show WORKING_ID
```

Replace the ID placeholders with IDs printed by `list`. `diff` and `show` also accept paths to exported receipt JSON files. A comparison covers:

- The command, working directory and file-selection rules.
- Interpreter version, implementation, executable, OS and architecture.
- Added, removed or changed installed distribution versions.
- Content changes in the selected starting files.
- Changes in selected environment variables, without printing their values.
- Commit, tracked-file dirty state and command exit code.
- Files added, removed or modified between each run's starting and final snapshots.

The timestamps and elapsed times remain in the receipts but are not treated as input differences. This is a debugging record, not a benchmark harness.

### HTML and JSON reports

```sh
runreceipt diff WORKING_ID FAILING_ID --format html > comparison.html
runreceipt diff WORKING_ID FAILING_ID --format json > comparison.json
```

The HTML report is a single file with no JavaScript, fonts or external resources. It can be opened offline. Names and values are escaped before rendering. The HTML view abbreviates file fingerprints; full hashes remain in the JSON receipt and comparison. The JSON report is useful for scripts or CI artifacts.

To fail a check when there are differences, file mutations, capture errors or incomparable environment fingerprints:

```sh
runreceipt diff WORKING_ID FAILING_ID --check
```

Without `--check`, a successful comparison returns `0` even when it finds changes. Invalid receipts and other tool errors return `2`. `run` returns the command's exit code; if the command succeeds but the final capture fails, it returns `2` and saves an incomplete receipt. Tool errors can also return `2` before execution. Check stderr and the saved receipt to distinguish these cases.

## Choose what gets captured

File contents are not copied into a receipt. Only paths, sizes and SHA-256 hashes are stored. Files are selected explicitly with repeatable `--track` arguments. Without `--track`, no files are hashed.

```sh
runreceipt run --track . --exclude 'datasets/*' --env RUN_MODE -- app.py
```

Exclusions use case-sensitive Python `fnmatch` patterns over relative paths; `*` can match `/`. The recorder always skips `.git`, `.runreceipt`, `.venv`, `venv`, `__pycache__`, `node_modules`, `target`, `build` and `dist` path components. `.gitignore` is not used. Symlinks and special files in a selected input cause a capture error; exclude them or select a narrower path. Missing selections fail before the command starts. A file deleted during the command is recorded as removed.

If two receipts use different file selections, the report says so. An added or removed observed file can then reflect changed coverage rather than a change to the same input set.

Use `--root` before the subcommand to work with another project:

```sh
runreceipt --root ./backend run --track src -- app.py
runreceipt --root ./backend list
```

### Environment values

Only variables selected by `--env` are fingerprinted. An unset variable is distinct from a variable set to an empty string. Values use HMAC-SHA-256 with a random local key at `.runreceipt/key`; the value itself and the key are not placed in a receipt.

Receipts from the same project key can detect value changes. Receipts using different keys can compare set/unset states, but the report marks their present values as incomparable. Keep the key local. Copying only receipt files to another machine still permits comparisons with their original key IDs; it does not make fingerprints from independently initialized projects comparable.

The command's arguments, absolute project and interpreter paths, package names, selected file names and content hashes are stored. Keep credentials out of command arguments, and choose source files or configuration templates rather than credential files for tracking. A receipt is a local debugging artifact, not an automatic redaction of every field.

## Try the demo

```sh
python examples/demo.py --output demo-report.html
```

The demo makes two real runs in a temporary project. The second uses different input data and a different environment value, then exits with a failure. It writes a comparison report and removes the temporary project. The tool does not send telemetry or upload receipts; any networking performed by a recorded command is that command's own behavior.

## Limits

A difference is evidence, not proof of cause. There is no dependency tracing or automatic replay. Only selected files and variables are captured. The recorder does not observe temporary writes that are undone before the final snapshot, files accessed elsewhere, imported module provenance, GPU state, remote services, random seeds, time-dependent behavior or the complete subprocess tree.

Package metadata comes from the selected interpreter's normal startup in the project directory. It is not an import graph, and command flags such as `-S` or application changes to `sys.path` can change what the application can actually import. Interpreter startup hooks may run during metadata collection. The recorder executes the command you provide; it does not isolate it or make it safe.

File snapshots are sequential, not a filesystem transaction. A file changing while it is being hashed normally raises an error, but unrelated concurrent changes are not comprehensively detected. Receipt publication uses local atomic hard links, so storage must be on a filesystem that supports them. Concurrent runs share the project key but get separate receipt IDs.

## Development

```sh
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

Tests cover actual command execution and exit codes, selected-input changes, keyed environment comparisons, concurrent initialization, malformed receipts and HTML escaping. CI runs on Linux, macOS and Windows with Python 3.10 and 3.15, then installs the built wheel before testing it.

MIT licensed. See [LICENSE](LICENSE).
