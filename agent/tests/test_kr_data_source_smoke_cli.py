"""CLI contracts for Korean data-source smoke checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch


def test_data_source_smoke_parser_registers_command() -> None:
    from cli._legacy import _build_parser

    args = _build_parser().parse_args(["data-source", "smoke"])

    assert args.command == "data-source"
    assert args.data_source_command == "smoke"
    assert args.allow_data_calls is False


def test_data_source_smoke_audit_parser_registers_command(tmp_path: Path) -> None:
    from cli._legacy import _build_parser

    evidence_path = tmp_path / "kr-data-source-smoke.json"
    args = _build_parser().parse_args(
        [
            "data-source",
            "smoke-audit",
            "--evidence",
            str(evidence_path),
            "--require-data-calls",
            "--json",
        ]
    )

    assert args.command == "data-source"
    assert args.data_source_command == "smoke-audit"
    assert args.evidence == evidence_path
    assert args.require_data_calls is True
    assert args.data_source_json is True


def test_data_source_smoke_audit_dispatches_to_handler(tmp_path: Path) -> None:
    from cli._legacy import EXIT_SUCCESS, main

    evidence_path = tmp_path / "kr-data-source-smoke.json"
    output_path = tmp_path / "audit" / "kr-data-source-smoke-audit.json"
    with patch("cli._legacy.cmd_data_source_smoke_audit", return_value=EXIT_SUCCESS) as audit:
        assert (
            main(
                [
                    "data-source",
                    "smoke-audit",
                    "--evidence",
                    str(evidence_path),
                    "--require-data-calls",
                    "--json",
                    "--output",
                    str(output_path),
                ]
            )
            == EXIT_SUCCESS
        )

    audit.assert_called_once_with(
        evidence_path=evidence_path,
        require_data_calls=True,
        json_mode=True,
        output_path=output_path,
    )


def test_data_source_smoke_cli_prints_plan_without_data_calls(
    capsys,
) -> None:
    from cli._legacy import EXIT_SUCCESS, main

    plan = {
        "status": "planned",
        "allow_data_calls_required": True,
        "steps": [{"operation": "krx_daily"}],
    }
    with patch(
        "backtest.loaders.kr_data_smoke.build_smoke_plan",
        return_value=plan,
    ) as build:
        with patch("backtest.loaders.kr_data_smoke.run_smoke") as run:
            assert main(["data-source", "smoke", "--json"]) == EXIT_SUCCESS

    build.assert_called_once_with(
        operations=None,
        symbol="005930.KS",
        start_date="2026-01-02",
        end_date="2026-01-02",
        nation_code="KR",
    )
    run.assert_not_called()
    payload = json.loads(capsys.readouterr().out)
    assert payload == plan


def test_data_source_smoke_cli_requires_explicit_opt_in_for_data_calls(
    capsys,
) -> None:
    from cli._legacy import EXIT_SUCCESS, main

    result = {
        "status": "passed",
        "checks": [{"operation": "koscom_holidays", "status": "passed"}],
    }
    with patch(
        "backtest.loaders.kr_data_smoke.run_smoke",
        return_value=result,
    ) as run:
        assert (
            main(
                [
                    "data-source",
                    "smoke",
                    "--allow-data-calls",
                    "--operation",
                    "koscom_holidays",
                    "--symbol",
                    "035720.KQ",
                    "--start-date",
                    "2026-02-02",
                    "--end-date",
                    "2026-02-03",
                    "--nation-code",
                    "kr",
                    "--json",
                ]
            )
            == EXIT_SUCCESS
        )

    run.assert_called_once_with(
        allow_data_calls=True,
        operations=["koscom_holidays"],
        symbol="035720.KQ",
        start_date="2026-02-02",
        end_date="2026-02-03",
        nation_code="kr",
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == result


def test_data_source_smoke_cli_maps_blocked_result_to_failure() -> None:
    from cli._legacy import EXIT_RUN_FAILED, main

    with patch(
        "backtest.loaders.kr_data_smoke.run_smoke",
        return_value={"status": "blocked", "checks": []},
    ):
        assert (
            main(["data-source", "smoke", "--allow-data-calls", "--json"])
            == EXIT_RUN_FAILED
        )


def test_data_source_smoke_cli_writes_plan_evidence_file(tmp_path) -> None:
    from cli._legacy import EXIT_SUCCESS, main

    output_path = tmp_path / "nested" / "kr-data-source-smoke.json"
    plan = {
        "status": "planned",
        "allow_data_calls_required": True,
        "steps": [{"operation": "krx_daily"}],
    }
    with patch(
        "backtest.loaders.kr_data_smoke.build_smoke_plan",
        return_value=plan,
    ):
        assert (
            main(["data-source", "smoke", "--output", str(output_path)])
            == EXIT_SUCCESS
        )

    assert json.loads(output_path.read_text(encoding="utf-8")) == plan
    assert output_path.stat().st_mode & 0o777 == 0o600


def test_data_source_smoke_cli_writes_explicit_smoke_evidence_file(tmp_path) -> None:
    from cli._legacy import EXIT_SUCCESS, main

    output_path = tmp_path / "kr-data-source-smoke-result.json"
    result = {
        "status": "passed",
        "checks": [{"operation": "krx_daily", "status": "passed"}],
    }
    with patch(
        "backtest.loaders.kr_data_smoke.run_smoke",
        return_value=result,
    ):
        assert (
            main(
                [
                    "data-source",
                    "smoke",
                    "--allow-data-calls",
                    "--output",
                    str(output_path),
                ]
            )
            == EXIT_SUCCESS
        )

    assert json.loads(output_path.read_text(encoding="utf-8")) == result
    assert output_path.stat().st_mode & 0o777 == 0o600


def _write_smoke_evidence(tmp_path: Path, payload: dict[str, Any]) -> Path:
    evidence_path = tmp_path / "kr-data-source-smoke.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    return evidence_path


def test_data_source_smoke_audit_accepts_plan_only_evidence_without_call_requirement(
    tmp_path: Path,
    capsys,
) -> None:
    from cli._legacy import EXIT_SUCCESS, cmd_data_source_smoke_audit

    evidence_path = _write_smoke_evidence(
        tmp_path,
        {
            "status": "planned",
            "steps": [{"operation": "krx_daily", "source": "krx", "read_only": True}],
            "sources": [{"source": "krx", "configured": False}],
        },
    )

    assert cmd_data_source_smoke_audit(evidence_path=evidence_path, json_mode=True) == EXIT_SUCCESS

    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "ok"
    assert audit["smoke_status"] == "planned"
    assert audit["data_calls_proven"] is False
    assert audit["plan_step_count"] == 1


def test_data_source_smoke_audit_fails_when_data_calls_required_but_not_proven(
    tmp_path: Path,
    capsys,
) -> None:
    from cli._legacy import EXIT_RUN_FAILED, cmd_data_source_smoke_audit

    evidence_path = _write_smoke_evidence(
        tmp_path,
        {
            "status": "blocked",
            "checks": [{"operation": "krx_daily", "source": "krx", "status": "blocked"}],
        },
    )

    assert (
        cmd_data_source_smoke_audit(
            evidence_path=evidence_path,
            require_data_calls=True,
            json_mode=True,
        )
        == EXIT_RUN_FAILED
    )

    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "failed"
    assert audit["reason"] == "data_calls_not_proven"
    assert audit["data_calls_proven"] is False
    assert audit["check_count"] == 1


def test_data_source_smoke_audit_accepts_passed_check_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    from cli._legacy import EXIT_SUCCESS, cmd_data_source_smoke_audit

    evidence_path = _write_smoke_evidence(
        tmp_path,
        {
            "status": "passed",
            "checks": [{"operation": "krx_daily", "source": "krx", "status": "passed", "rows": 3}],
        },
    )

    assert (
        cmd_data_source_smoke_audit(
            evidence_path=evidence_path,
            require_data_calls=True,
            json_mode=True,
        )
        == EXIT_SUCCESS
    )

    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "ok"
    assert audit["data_calls_proven"] is True
    assert audit["passed_check_count"] == 1


def test_data_source_smoke_audit_rejects_secret_markers_in_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    from cli._legacy import EXIT_RUN_FAILED, cmd_data_source_smoke_audit

    evidence_path = _write_smoke_evidence(
        tmp_path,
        {
            "status": "passed",
            "checks": [{"operation": "krx_daily", "source": "krx", "status": "passed"}],
            "api_key": "should-not-be-in-evidence",
        },
    )

    assert cmd_data_source_smoke_audit(evidence_path=evidence_path, json_mode=True) == EXIT_RUN_FAILED

    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "failed"
    assert audit["reason"] == "secret_marker_detected"
    assert audit["secret_markers"] == ["api_key"]


def test_data_source_smoke_audit_writes_private_audit_report(tmp_path: Path) -> None:
    from cli._legacy import EXIT_SUCCESS, cmd_data_source_smoke_audit

    evidence_path = _write_smoke_evidence(
        tmp_path,
        {
            "status": "planned",
            "steps": [{"operation": "krx_daily", "source": "krx", "read_only": True}],
        },
    )
    output_path = tmp_path / "nested" / "kr-data-source-smoke-audit.json"

    assert (
        cmd_data_source_smoke_audit(
            evidence_path=evidence_path,
            output_path=output_path,
        )
        == EXIT_SUCCESS
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["smoke_status"] == "planned"
    assert payload["data_calls_proven"] is False
    assert output_path.stat().st_mode & 0o777 == 0o600
