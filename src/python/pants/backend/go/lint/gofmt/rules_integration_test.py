# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from textwrap import dedent

import pytest

from pants.backend.go.lint import fmt
from pants.backend.go.lint.gofmt.rules import GofmtFieldSet, GofmtRequest
from pants.backend.go.lint.gofmt.rules import rules as gofmt_rules
from pants.backend.go.target_types import GoBinary, GoPackage
from pants.core.goals.fmt import FmtResult
from pants.core.goals.lint import LintResult, LintResults
from pants.core.util_rules import external_tool, source_files
from pants.core.util_rules.source_files import SourceFiles, SourceFilesRequest
from pants.engine.addresses import Address
from pants.engine.fs import CreateDigest, Digest, FileContent
from pants.engine.target import Target
from pants.testutil.rule_runner import QueryRule, RuleRunner


@pytest.fixture()
def rule_runner() -> RuleRunner:
    return RuleRunner(
        target_types=[GoBinary, GoPackage],
        rules=[
            *external_tool.rules(),
            *fmt.rules(),
            *gofmt_rules(),
            *source_files.rules(),
            QueryRule(LintResults, (GofmtRequest,)),
            QueryRule(FmtResult, (GofmtRequest,)),
            QueryRule(SourceFiles, (SourceFilesRequest,)),
        ],
    )


GOOD_FILE = dedent(
    """\
    package grok

    import (
    \t"fmt"
    )

    func Grok(s string) {
    \tfmt.Println(s)
    }
    """
)

BAD_FILE = dedent(
    """\
    package grok
    import (
    "fmt"
    )

    func Grok(s string) {
    fmt.Println(s)
    }
    """
)

FIXED_BAD_FILE = dedent(
    """\
    package grok

    import (
    \t"fmt"
    )

    func Grok(s string) {
    \tfmt.Println(s)
    }
    """
)


def run_gofmt(
    rule_runner: RuleRunner,
    targets: list[Target],
    *,
    extra_args: list[str] | None = None,
) -> tuple[tuple[LintResult, ...], FmtResult]:
    args = ["--backend-packages=pants.backend.go", *(extra_args or ())]
    rule_runner.set_options(args)
    field_sets = [GofmtFieldSet.create(tgt) for tgt in targets]
    lint_results = rule_runner.request(LintResults, [GofmtRequest(field_sets)])
    input_sources = rule_runner.request(
        SourceFiles,
        [
            SourceFilesRequest(field_set.sources for field_set in field_sets),
        ],
    )
    fmt_result = rule_runner.request(
        FmtResult,
        [
            GofmtRequest(field_sets, prior_formatter_result=input_sources.snapshot),
        ],
    )
    return lint_results.results, fmt_result


def get_digest(rule_runner: RuleRunner, source_files: dict[str, str]) -> Digest:
    files = [FileContent(path, content.encode()) for path, content in source_files.items()]
    return rule_runner.request(Digest, [CreateDigest(files)])


def test_passing(rule_runner: RuleRunner) -> None:
    rule_runner.write_files({"f.go": GOOD_FILE, "BUILD": "go_package(name='t')"})
    tgt = rule_runner.get_target(Address("", target_name="t"))
    lint_results, fmt_result = run_gofmt(rule_runner, [tgt])
    assert len(lint_results) == 1
    assert lint_results[0].exit_code == 0
    assert lint_results[0].stderr == ""
    assert fmt_result.stdout == ""
    assert fmt_result.output == get_digest(rule_runner, {"f.go": GOOD_FILE})
    assert fmt_result.did_change is False


def test_failing(rule_runner: RuleRunner) -> None:
    rule_runner.write_files({"f.go": BAD_FILE, "BUILD": "go_package(name='t')"})
    tgt = rule_runner.get_target(Address("", target_name="t"))
    lint_results, fmt_result = run_gofmt(rule_runner, [tgt])
    assert len(lint_results) == 1
    assert lint_results[0].exit_code == 1
    assert "f.go" in lint_results[0].stdout
    assert fmt_result.stderr == ""
    assert fmt_result.output == get_digest(rule_runner, {"f.go": FIXED_BAD_FILE})
    assert fmt_result.did_change is True


def test_mixed_sources(rule_runner: RuleRunner) -> None:
    rule_runner.write_files(
        {"good.go": GOOD_FILE, "bad.go": BAD_FILE, "BUILD": "go_package(name='t')"}
    )
    tgt = rule_runner.get_target(Address("", target_name="t"))
    lint_results, fmt_result = run_gofmt(rule_runner, [tgt])
    assert len(lint_results) == 1
    assert lint_results[0].exit_code == 1
    assert "bad.go" in lint_results[0].stdout
    assert "good.go" not in lint_results[0].stdout
    assert fmt_result.output == get_digest(
        rule_runner, {"good.go": GOOD_FILE, "bad.go": FIXED_BAD_FILE}
    )
    assert fmt_result.did_change is True


def test_multiple_targets(rule_runner: RuleRunner) -> None:
    rule_runner.write_files(
        {
            "good/f.go": GOOD_FILE,
            "good/BUILD": "go_package()",
            "bad/f.go": BAD_FILE,
            "bad/BUILD": "go_package()",
        }
    )
    tgts = [
        rule_runner.get_target(Address("good")),
        rule_runner.get_target(Address("bad")),
    ]
    lint_results, fmt_result = run_gofmt(rule_runner, tgts)
    assert len(lint_results) == 1
    assert lint_results[0].exit_code == 1
    assert "bad/f.go" in lint_results[0].stdout
    assert "good/f.go" not in lint_results[0].stdout
    assert fmt_result.output == get_digest(
        rule_runner, {"good/f.go": GOOD_FILE, "bad/f.go": FIXED_BAD_FILE}
    )
    assert fmt_result.did_change is True


def test_skip(rule_runner: RuleRunner) -> None:
    rule_runner.write_files({"f.go": BAD_FILE, "BUILD": "go_package(name='t')"})
    tgt = rule_runner.get_target(Address("", target_name="t"))
    lint_results, fmt_result = run_gofmt(rule_runner, [tgt], extra_args=["--gofmt-skip"])
    assert not lint_results
    assert fmt_result.skipped is True
    assert fmt_result.did_change is False
