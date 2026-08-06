# Contributing

Use Python 3.12/3.13 and a virtual environment. Install `requirements-dev.txt` and the editable package; run `make check`, static checks and relevant integration tests. Do not commit `.env`, cloud state, model weights, backups or unauthorized source material.

A pipeline change should include a regression test, updated configuration/schema notes and a decision record when it changes publication or trust boundaries. Do not weaken quality thresholds merely to turn a failing fixture green. Tests using fakes must be named/documented as such.

Keep new storage/index side effects behind interfaces. Preserve the run-scoped data contract, explicit model identity, lineage and the single active-pointer publication boundary. Document migration/rollback semantics before changing release schema version 1.

Submit security issues privately through the hosting repository's security advisory mechanism. Review dependency/license changes and actual scan results. No benchmark number belongs in the README without its hardware, workload and measurement scope.
