# Test fixtures

`SampleProject` is a minimal F# project that the integration tests
(`tests/test_integration.py`) drive real `fsautocomplete` against. It is
deliberately small: two source files with a known reference topology, plus one
that does not compile.

| File | Why it exists |
|---|---|
| `Library.fs` | Declares `answer` and `double`. `double` sits at **line 7, column 5** — the integration test queries that exact position, so do not reformat this file without updating the test. |
| `Consumer.fs` | Uses `double` twice in one expression and `answer` once, so `references` has a cross-file result to find: 3 hits in 2 files, counting the declaration. |
| `Broken.fs` | **Does not compile, on purpose.** See below. |

## Broken.fs does not compile, and that is the point

`Broken.fs` references `nonExistentFunction`, which does not exist, producing a
certain **FS0039**. It exists so `test_diagnostics_reports_the_deliberate_error`
has something guaranteed to find — a diagnostics test needs a diagnostic, and one
that depends on a real mistake somewhere else in the tree would rot.

**If your IDE flags an error here, that is the fixture working.** Please do not
report it as a bug, and do not "fix" it — the integration suite fails if you do.

It does not disturb anything else. `dotnet restore` does not compile, so project
loading is unaffected, and the other three integration tests pass against a
project that contains it.

## Restoring

FSAC loads projects through MSBuild, so the project must be restored before the
integration tests can analyse it. The suite does this itself in a session-scoped
fixture, but to do it by hand:

```bash
cd tests/fixtures/SampleProject && dotnet restore
```

`bin/` and `obj/` are gitignored.
