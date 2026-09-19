"""Public-extension arithmetic/receipt checks with the exact derived dependency view.

This is automated verification by a separately written program, not a second
human contributor's reproduction and not a proof that every model is correct.
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from research.final_evaluation import combine_years, load_input
from research.extension_release_protocol import verification_protocol
from solar_recovery.baselines_v3 import geometry
from solar_recovery.pilot import digest
from solar_recovery.replay import observations_from_hourly
from solar_recovery.replay_v3 import Fault, LAGS, deliver_schedule
from solar_recovery.replay_v4 import stale_schedule


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def independently_score(actual, quantiles):
    levels = np.array([.05, .1, .25, .5, .75, .9, .95])
    errors = actual[:, None]-quantiles
    return (2./7)*np.sum((levels-(errors < 0))*errors, axis=1)


def expected_phases(origins, faults):
    """Independent half-open scheduled phases; first active event takes priority."""
    origins = pd.DatetimeIndex(origins)
    event = np.full(len(origins), -1, dtype=int)
    phase = np.full(len(origins), "normal", dtype=object)
    age = np.full(len(origins), np.nan)
    for i, fault in enumerate(faults):
        returns = sorted((pd.Timestamp(fault.pv_return), pd.Timestamp(fault.irradiance_return)))
        active = (event == -1) & (origins >= pd.Timestamp(fault.start)) & (origins < returns[1]+pd.Timedelta(hours=24))
        event[active] = i
        phase[active & (origins < returns[0])] = "outage"
        phase[active & (origins >= returns[0]) & (origins < returns[1])] = "partial_restoration"
        recovering = active & (origins >= returns[1])
        age[recovering] = (origins[recovering]-returns[1]).total_seconds()/3600
        phase[recovering & (age < 6)] = "recovery_0_6"
        phase[recovering & (age >= 6)] = "recovery_6_24"
    return pd.DataFrame({"phase": phase, "event_id": event, "recovery_hour": age}, index=origins)


def expected_label_updates(features, schedule, contract, horizons):
    first = {}
    for observation in schedule:
        if observation.stream == "pv":
            first[observation.end] = min(first.get(observation.end, observation.receipt), observation.receipt)
    receipts = pd.Series(first)
    updates, issued = np.zeros(len(features), dtype=int), 0
    for h in horizons:
        ends = features.index.floor("h")+pd.Timedelta(hours=h)
        daylight = geometry(ends, contract) > 0
        issued += int(daylight.sum())
        received = pd.DatetimeIndex(receipts.reindex(ends))
        positions = features.index.searchsorted(received)
        eligible = daylight & received.notna() & (positions < len(features))
        np.add.at(updates, positions[eligible], 1)
    return updates, issued-int(updates.sum())


def verify(root, release_lock=None):
    root = Path(root)
    output = root/"verification.json"
    if output.exists():
        raise FileExistsError("Verification records are immutable")
    manifest = json.loads((root/"manifest.json").read_text())
    require(manifest["status"] == "complete frozen evaluation", "Run is not complete")
    config = json.loads((root/"config.json").read_text())
    frozen, protocol_provenance = verification_protocol(root/"config.json", root/"protocol_lock.json", release_lock)
    for name, value in manifest["code_sha256"].items():
        require(digest(root/"source"/name) == value, f"Changed archived code {name}")
    require(digest(root/"protocol_lock.json") == manifest["freeze_sha256"], "Changed freeze archive")
    for key, info in manifest["training"].items():
        site, year, variant, ablation = key.split("/")
        model = root/site/f"models_{year}_{variant}_{ablation}.pkl"
        require(digest(model) == info["model_sha256"], "Fitted-model checksum mismatch")
        require(pd.Timestamp(info["latest_donor_end"]) <= pd.Timestamp(f"{int(year)+1}-01-01T00:00Z"), "Future training donor")
    rng = np.random.default_rng(70231)
    checks, total, receipt_slots = [], 0, 0
    keys = ["origin", "horizon"]
    quantile_names = [f"q{p:02d}" for p in (5, 10, 25, 50, 75, 90, 95)]
    for site in config["sites"]:
        for case in config["cases"]:
            if site not in case.get("sites", config["sites"]):
                continue
            name = f"{site}/{case['id']}"
            print(f"Verifying {name}", flush=True)
            record = manifest["cases"][name]
            path = root/site/f"forecasts_{case['id']}.parquet"
            require(digest(path) == record["forecasts_sha256"], "Forecast checksum mismatch")
            feature_path = root/site/f"features_{case['id']}.parquet"
            require(digest(feature_path) == record["features_sha256"], "Feature checksum mismatch")
            scored = pd.read_parquet(path)
            features = pd.read_parquet(feature_path)
            require(not scored.duplicated([*keys, "method"]).any(), "Duplicate forecast keys")
            require(scored.origin.isin(features.index).all(), "Missing feature provenance")
            require((scored.target_end == scored.origin.dt.floor("h")+pd.to_timedelta(scored.horizon, unit="h")).all(), "Wrong target end")
            require((scored.target_start == scored.target_end-pd.Timedelta(hours=1)).all(), "Wrong target start")
            require(scored.actual_lead_minutes.eq(scored.horizon*60-case["receipt_minutes"]).all(), "Wrong actual lead")
            require(~((features.index >= pd.Timestamp(config["warmup_end"])) &
                       (features.index < pd.Timestamp(config["evaluation_start"]))).any(), "Purged origins were forecast")
            frames = [load_input(config, site, y, case["data_variant"])[0] for y in (2016, 2017)]
            truth = combine_years(frames)
            capacity = load_input(config, site, 2016, case["data_variant"])[1]["capacity_kw_dc"]
            actual = truth.pv.reindex(pd.DatetimeIndex(scored.target_end)).to_numpy()
            np.testing.assert_allclose(scored.actual_kw, actual, equal_nan=True, rtol=0, atol=0)
            require(scored.valid_target.eq(np.isfinite(actual)).all(), "Target eligibility mismatch")
            poa = truth.irradiance.reindex(pd.DatetimeIndex(scored.target_end)).to_numpy()
            require(scored.zero_with_bright_poa.eq((actual == 0) & (poa > 200)).all(), "Ambiguity flag mismatch")
            q = scored[quantile_names].to_numpy()
            require(np.isfinite(q).all() and (q >= 0).all() and (np.diff(q, axis=1) >= 0).all(), "Invalid issued quantiles")
            np.testing.assert_allclose(scored.nwis, independently_score(actual, q)/capacity, rtol=1e-12, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(scored.nmae, abs(actual-q[:, 3])/capacity, rtol=1e-12, atol=1e-12, equal_nan=True)
            for level, lo, hi in ((50, 2, 4), (80, 1, 5), (90, 0, 6)):
                expected = np.where(np.isfinite(actual), (actual >= q[:, lo]) & (actual <= q[:, hi]), np.nan)
                np.testing.assert_allclose(scored[f"coverage{level}"], expected, equal_nan=True)
                np.testing.assert_allclose(scored[f"nwidth{level}"], (q[:, hi]-q[:, lo])/capacity, atol=1e-12)
            raw = scored.loc[scored.method.eq("raw")].set_index(keys).sort_index()
            for method in config["primary_methods"]:
                part = scored.loc[scored.method.eq(method)].set_index(keys).sort_index()
                if len(part):
                    require(part.index.equals(raw.index), "Calibration row mismatch")
                    np.testing.assert_allclose(part.q50, raw.q50, rtol=0, atol=0)
            for method, part in scored.groupby("method"):
                require(part.set_index(keys).sort_index().index.equals(raw.index), f"Comparator row mismatch: {method}")
            events = observations_from_hourly(truth, case["receipt_minutes"])
            faults = [Fault(**f) for f in json.loads((root/site/f"schedule_{case['id']}.json").read_text())]
            phase_check = expected_phases(features.index, faults).reindex(pd.DatetimeIndex(scored.origin))
            require(np.array_equal(scored.phase.to_numpy(), phase_check.phase.to_numpy()), "Scheduled phase mismatch")
            require(np.array_equal(scored.event_id.to_numpy(), phase_check.event_id.to_numpy()), "Scheduled event mismatch")
            np.testing.assert_allclose(scored.recovery_hour, phase_check.recovery_hour, rtol=0, atol=0, equal_nan=True)
            schedule = stale_schedule(events, faults) if case.get("stale_transport", False) else deliver_schedule(events, faults)
            label_schedule = events if case.get("privileged_labels", False) else schedule
            contract = load_input(config, site, 2016, case["data_variant"])[1]
            require(scored.daylight.eq(geometry(pd.DatetimeIndex(scored.target_end), contract) > 0).all(), "Daylight eligibility mismatch")
            warmup = scored.origin.lt(pd.Timestamp(config["evaluation_start"]))
            require(np.array_equal(scored.period.to_numpy(), np.where(warmup, "warmup", "evaluation")), "Evaluation period mismatch")
            within = np.where(warmup, scored.target_end.le(pd.Timestamp(config["evaluation_start"])),
                              scored.target_end.le(pd.Timestamp(config["evaluation_end"])))
            require(scored.within_period.eq(within).all(), "Period boundary eligibility mismatch")
            expected_updates, expected_pending = expected_label_updates(features, label_schedule, contract, config["horizons"])
            diagnostics = pd.read_parquet(root/site/f"diagnostics_{case['id']}.parquet")
            for method, values in diagnostics.groupby("method"):
                repeated = values.groupby("origin").label_updates_at_origin_all_horizons
                require(repeated.nunique().eq(1).all(), "Inconsistent repeated update diagnostic")
                actual_updates = repeated.first().reindex(features.index)
                np.testing.assert_array_equal(actual_updates.to_numpy(), expected_updates)
                counts = record["calibration_updates"][method]
                require(counts["updates"] == int(expected_updates.sum()), "Wrong receipt-gated update total")
                require(counts["pending_forecasts"] == expected_pending, "Wrong pending forecast total")
            # Direct lookup from delivered packets, independent of observer state.
            # Check a random sample plus origins neighboring every interruption.
            selected = set(rng.choice(len(features), min(40, len(features)), replace=False).tolist())
            for fault in faults:
                for instant in (fault.start, fault.pv_return, fault.irradiance_return):
                    position = features.index.searchsorted(instant)
                    selected.update(i for i in (position-1, position, position+1) if 0 <= i < len(features))
            for i in sorted(selected):
                origin = features.index[i]
                expected_end = (origin-pd.Timedelta(minutes=case["receipt_minutes"])).floor("h")
                for stream in ("pv", "irradiance"):
                    visible = [o for o in schedule if o.stream == stream and o.receipt <= origin]
                    by_end = {o.end: o.value for o in visible}
                    expected_slots = [by_end.get(expected_end-pd.Timedelta(hours=lag-1), np.nan) for lag in LAGS]
                    stored_slots = features.iloc[i][[f"{stream}_lag{lag}" for lag in LAGS]].to_numpy()
                    np.testing.assert_allclose(stored_slots, expected_slots, equal_nan=True, rtol=0, atol=0)
                    receipt_slots += len(LAGS)
                    if visible:
                        latest = max(by_end)
                        np.testing.assert_allclose(features.iloc[i][f"{stream}_last"], by_end[latest], rtol=0, atol=0)
                        if case.get("model_ablation") != "no_age":
                            expected_age = max(0., (expected_end-latest)/pd.Timedelta(hours=1))
                            require(features.iloc[i][f"{stream}_age"] == expected_age, "Incorrect measurement age")
            count = len(scored)
            total += count
            checks.append({"site": site, "case_id": case["id"], "forecasts": count,
                "sampled_receipt_origins": len(selected), "all_scores_recomputed": True,
                "all_targets_match_source": True, "identical_method_rows": True,
                "all_scoring_phases_and_eligibility_verified": True})
    require(total == manifest["total_forecasts"], "Total forecast count mismatch")
    require(len(checks) == frozen["site_case_count"], "Incomplete site/case grid")
    result = {"status": "passed automated final verification", "forecasts": total,
        "receipt_slots_checked": receipt_slots, "cases": checks,
        "manifest_sha256": digest(root/"manifest.json"), "verifier_sha256": digest(Path(__file__)),
        "protocol_provenance": protocol_provenance, "protocol_checker_sha256": digest("research/release_protocol.py"),
        "files_sha256": {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).parts[0] not in {"completion_workflow", "analysis"}
            and p.name != "verification.json"},
        "scope": "All target values, score arithmetic, quantile validity, median invariance, scheduled phases/events/recovery hours, daylight and period eligibility, scoring-row identity and per-origin receipt-gated update counts; sampled direct delivery lookup; all scientific dependency hashes, with private-PRD verification or declared omission recorded in protocol_provenance",
        "limits": "Not an independent human reproduction, not a proof of all model/calibrator behavior or receipt-simulator realism"}
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(f"Passed {total:,} forecasts and {receipt_slots:,} independently looked-up history slots")


def prepare_public_context(root, release_lock):
    """Record authenticated public provenance for the unchanged analysis guard."""
    root = Path(root)
    if (root/'verification.json').exists() or (root/'extension_context.json').exists():
        raise FileExistsError('Public verification/context outputs are immutable')
    if json.loads((root/'manifest.json').read_text())['status'] != 'complete frozen evaluation':
        raise ValueError('Wait for completed public reproduction')
    _, provenance = verification_protocol(root/'config.json', root/'protocol_lock.json', release_lock)
    names = ['research/verify_public_extension.py', 'research/extension_release_protocol.py',
        'research/reproduce_public_extension.py', 'research/analyze_producing_extension.py']
    for name in names:
        target = root/'extension_source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, target)
    (root/'extension_context.json').write_text(json.dumps({
        'identity': 'public reproduction of separately frozen producing-system extension',
        'original_parent_authenticated': True, 'public_protocol_provenance': provenance,
        'extension_dependencies_verified': provenance['scientific_dependencies_verified'],
        'source_sha256': {name: digest(name) for name in names},
        'limits': 'Automated public reproduction; no independent human or physical-meter certification'}, indent=2)+'\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--release-lock", default="release/PRODUCING_EXTENSION_DEPENDENCY_LOCK.json", help="Exact validated public extension dependency view")
    args = parser.parse_args()
    prepare_public_context(args.run, args.release_lock)
    verify(args.run, args.release_lock)
