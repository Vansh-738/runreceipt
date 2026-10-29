# Contributing

A useful bug report includes the command, a small reproducible input and what the receipt or comparison got wrong. Replace private paths and package names when needed, and leave real credentials out of reports.

Add regression tests under `tests/`. Keep comparisons explicit about uncertainty: different capture coverage and different environment keys must not be presented as confirmed input changes. An incomplete final snapshot must not look like every file was deleted.

Keep receipt schema changes versioned. Avoid collecting new system details by default without explaining why they are needed. Run the development checks in the README before opening a pull request.
