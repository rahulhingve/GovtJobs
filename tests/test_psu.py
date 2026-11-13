from pathlib import Path
import pytest
from typer.testing import CliRunner
from govjobs.cli import app
from govjobs.psu import normalize_ratna_label, find_psu_match, sync_psu_registry, load_psu_registry

runner = CliRunner()

def test_normalize_ratna_label():
    # Maharatna
    r, ok = normalize_ratna_label("Maharatna")
    assert r == "maharatna" and ok
    r, ok = normalize_ratna_label("Maharatna[2]")
    assert r == "maharatna" and ok

    # Navratna
    r, ok = normalize_ratna_label("Navratna")
    assert r == "navratna" and ok
    r, ok = normalize_ratna_label("Navratna Category")
    assert r == "navratna" and ok
    r, ok = normalize_ratna_label("Navratna Category - I")
    assert r == "navratna" and ok

    # Miniratna Category I (including typos and lowercase l)
    for s in [
        "Miniratna Category - I",
        "Miniratna Category - l",
        "Miniratna Category-I",
        "Mini Ratna Company Category -1",
    ]:
        r, ok = normalize_ratna_label(s)
        assert r == "miniratna_1" and ok, f"Failed for {s}"

    # Miniratna Category II
    for s in ["Miniratna Category - II", "Miniratna Category II"]:
        r, ok = normalize_ratna_label(s)
        assert r == "miniratna_2" and ok, f"Failed for {s}"

    # None / Empty
    for s in ["", "-", "–", "None", "N/A"]:
        r, ok = normalize_ratna_label(s)
        assert r == "none" and ok

    # Unrecognised
    r, ok = normalize_ratna_label("SuperRatna Unknown")
    assert r == "none" and not ok

def test_find_psu_match():
    # Test matching with sample registry
    sample_registry = [
        {
            "name": "Bharat Heavy Electricals Limited",
            "aliases": ["BHEL"],
            "ratna_class": "maharatna",
            "ministry": "Ministry of Heavy Industries",
        },
        {
            "name": "Power Grid Corporation of India Limited",
            "aliases": ["POWERGRID", "Power Grid"],
            "ratna_class": "maharatna",
            "ministry": "Ministry of Power",
        },
        {
            "name": "Cochin Shipyard Limited",
            "aliases": ["CSL", "Cochin Shipyard"],
            "ratna_class": "miniratna_1",
            "ministry": "Ministry of Ports, Shipping and Waterways",
        }
    ]

    # Exact alias
    m1 = find_psu_match("BHEL", sample_registry)
    assert m1 is not None
    assert m1["name"] == "Bharat Heavy Electricals Limited"
    assert m1["ratna_class"] == "maharatna"

    # Token match in org string
    m2 = find_psu_match("Power Grid Corporation of India (POWERGRID)", sample_registry)
    assert m2 is not None
    assert m2["name"] == "Power Grid Corporation of India Limited"

    # Substring match
    m3 = find_psu_match("Cochin Shipyard Careers", sample_registry)
    assert m3 is not None
    assert m3["ratna_class"] == "miniratna_1"

    # Non-match
    m4 = find_psu_match("State Bank of India", sample_registry)
    assert m4 is None

def test_cli_psu_commands():
    # 1. jobs coverage --psu
    res_cov = runner.invoke(app, ["coverage", "--psu"])
    assert res_cov.exit_code == 0
    assert "Central Public Sector Undertakings (PSU) Coverage Status" in res_cov.stdout
    assert "Maharatna" in res_cov.stdout
    assert "PSU Coverage Summary" in res_cov.stdout

    # 2. jobs list --psu-class
    res_list_cls = runner.invoke(app, ["list", "--psu-class", "maharatna"])
    assert res_list_cls.exit_code == 0
    assert "Power Grid" in res_list_cls.stdout

    # 3. jobs list --psu
    res_list_psu = runner.invoke(app, ["list", "--psu", "POWERGRID"])
    assert res_list_psu.exit_code == 0
    assert "Power Grid" in res_list_psu.stdout
