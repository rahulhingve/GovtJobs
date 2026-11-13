import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from govjobs.models import Job
from govjobs.status import compute_job_status, JobStatus, job_sort_key
from govjobs.utils import fmt_date, fmt_datetime_ist, days_left, get_ist_today, IST

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GovJobs - Permanent Indian Government BTech Recruitments</title>
    <style>
        :root {
            --bg: #0b1120;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --primary-hover: #0284c7;
            --accent: #6366f1;
            --expiring-bg: #450a0a;
            --expiring-border: #ef4444;
            --expiring-text: #fca5a5;
            --active-bg: #052e16;
            --active-border: #22c55e;
            --active-text: #86efac;
            --upcoming-bg: #172554;
            --upcoming-border: #3b82f6;
            --upcoming-text: #93c5fd;
            --unverified-bg: #451a03;
            --unverified-border: #f59e0b;
            --unverified-text: #fde68a;
            --closed-bg: #1e293b;
            --closed-border: #64748b;
            --closed-text: #94a3b8;
        }

        @media (prefers-color-scheme: light) {
            :root {
                --bg: #f8fafc;
                --surface: #ffffff;
                --surface-hover: #f1f5f9;
                --border: #cbd5e1;
                --text: #0f172a;
                --text-muted: #64748b;
                --primary: #0284c7;
                --primary-hover: #0369a1;
                --accent: #4f46e5;
                --expiring-bg: #fef2f2;
                --expiring-border: #ef4444;
                --expiring-text: #991b1b;
                --active-bg: #f0fdf4;
                --active-border: #22c55e;
                --active-text: #166534;
                --upcoming-bg: #eff6ff;
                --upcoming-border: #3b82f6;
                --upcoming-text: #1e40af;
                --unverified-bg: #fffbeb;
                --unverified-border: #f59e0b;
                --unverified-text: #92400e;
                --closed-bg: #f1f5f9;
                --closed-border: #94a3b8;
                --closed-text: #475569;
            }
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 16px 20px 40px;
        }

        .container { max-width: 1240px; margin: 0 auto; }

        header {
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        .header-top {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: baseline;
            gap: 12px;
        }
        h1 { font-size: 1.6rem; color: var(--primary); font-weight: 700; letter-spacing: -0.5px; }
        .subtitle { color: var(--text-muted); font-size: 0.9rem; margin-top: 4px; }
        .updated-time { font-size: 0.8rem; color: var(--text-muted); }

        .summary-stats {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 14px;
        }
        .stat-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.82rem;
            font-weight: 600;
        }
        .stat-expiring { background: var(--expiring-bg); border: 1px solid var(--expiring-border); color: var(--expiring-text); }
        .stat-active { background: var(--active-bg); border: 1px solid var(--active-border); color: var(--active-text); }
        .stat-upcoming { background: var(--upcoming-bg); border: 1px solid var(--upcoming-border); color: var(--upcoming-text); }
        .stat-total { background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); }

        /* Tabs */
        .tabs {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            border-bottom: 2px solid var(--border);
            margin-bottom: 18px;
            padding-bottom: 2px;
        }
        .tab-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 8px 16px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            border-radius: 6px 6px 0 0;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 6px;
            border-bottom: 3px solid transparent;
            margin-bottom: -5px;
        }
        .tab-btn:hover { color: var(--text); background: var(--surface-hover); }
        .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
        .tab-badge {
            background: var(--surface);
            padding: 1px 7px;
            border-radius: 10px;
            font-size: 0.75rem;
            font-weight: 700;
        }

        /* Sticky Filters Bar */
        .filters-bar {
            position: sticky;
            top: 0;
            z-index: 50;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .filter-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }
        .search-box {
            flex: 1 1 240px;
            position: relative;
        }
        input, select {
            width: 100%;
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 7px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            outline: none;
        }
        input:focus-visible, select:focus-visible, button:focus-visible {
            outline: 2px solid var(--primary);
        }
        select { cursor: pointer; width: auto; min-width: 130px; }

        .chips-group {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            align-items: center;
            margin-top: 10px;
        }
        .chip-label { font-size: 0.78rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-right: 4px; }
        .chip {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 0.76rem;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
        }
        .chip:hover { border-color: var(--primary); color: var(--text); }
        .chip.active { background: var(--primary); color: #0f172a; border-color: var(--primary); font-weight: 700; }

        .options-row {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
            font-size: 0.82rem;
            color: var(--text-muted);
        }
        .checkbox-label {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            user-select: none;
        }
        .checkbox-label input { width: auto; margin: 0; }

        /* Cards Grid */
        .cards-list { display: flex; flex-direction: column; gap: 14px; }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px 20px;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .card:hover {
            border-color: var(--primary);
            box-shadow: 0 4px 14px rgba(0,0,0,0.12);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 6px;
        }
        .org-wrap {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
        }
        .org-name {
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--primary);
        }
        .ratna-badge {
            background: #312e81;
            color: #c7d2fe;
            border: 1px solid #4f46e5;
            padding: 1px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .days-chip {
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 800;
            white-space: nowrap;
        }
        .days-red { background: var(--expiring-bg); border: 1px solid var(--expiring-border); color: var(--expiring-text); }
        .days-orange { background: var(--unverified-bg); border: 1px solid var(--unverified-border); color: var(--unverified-text); }
        .days-green { background: var(--active-bg); border: 1px solid var(--active-border); color: var(--active-text); }
        .days-blue { background: var(--upcoming-bg); border: 1px solid var(--upcoming-border); color: var(--upcoming-text); }
        .days-gray { background: var(--closed-bg); border: 1px solid var(--closed-border); color: var(--closed-text); }

        .post-title {
            font-size: 1.18rem;
            font-weight: 700;
            color: var(--text);
            margin: 4px 0 10px;
            line-height: 1.35;
        }

        .tags-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 12px;
        }
        .tag {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.76rem;
            font-weight: 600;
        }
        .tag-branch { border-color: var(--primary); color: var(--primary); }
        .tag-gate { border-color: #f59e0b; color: #f59e0b; }
        .tag-vacancies { border-color: #10b981; color: #10b981; }

        .requirements-list {
            font-size: 0.82rem;
            color: var(--text-muted);
            margin-bottom: 12px;
            padding-left: 18px;
        }
        .requirements-list li { margin-bottom: 2px; }

        .meta-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 6px 16px;
            font-size: 0.82rem;
            color: var(--text-muted);
            margin-bottom: 14px;
            padding-top: 10px;
            border-top: 1px solid var(--border);
        }
        .meta-grid span strong { color: var(--text); }

        .card-actions {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding-top: 10px;
            border-top: 1px solid var(--border);
        }
        .btn-group { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.82rem;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            border: 1px solid transparent;
        }
        .btn-primary { background: var(--primary); color: #0f172a; }
        .btn-primary:hover { background: var(--primary-hover); }
        .btn-secondary { background: var(--bg); border-color: var(--border); color: var(--text); }
        .btn-secondary:hover { background: var(--surface-hover); }
        .official-note { font-size: 0.74rem; color: var(--text-muted); font-style: italic; }

        .pagination-bar {
            text-align: center;
            margin-top: 24px;
        }
        .btn-show-more {
            background: var(--surface);
            color: var(--primary);
            border: 1px solid var(--border);
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 700;
            cursor: pointer;
        }
        .btn-show-more:hover { background: var(--surface-hover); border-color: var(--primary); }

        .no-jobs {
            text-align: center;
            padding: 40px 20px;
            background: var(--surface);
            border-radius: 8px;
            border: 1px dashed var(--border);
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        /* Print styles */
        @media print {
            body { background: #fff !important; color: #000 !important; padding: 0 !important; }
            .filters-bar, .tabs, .btn-group, .pagination-bar { display: none !important; }
            .card { break-inside: avoid; border: 1px solid #ccc !important; box-shadow: none !important; margin-bottom: 12px; }
            .btn { display: none !important; }
        }
    </style>
</head>
<body>
<div class="container">
    <header>
        <div class="header-top">
            <div>
                <h1>GovJobs</h1>
                <div class="subtitle">Indian Government Permanent BTech/BE Job Tracker (PSUs, Central Boards, State PSCs)</div>
            </div>
            <div class="updated-time" id="updated-time">Last updated: __UPDATED_AT__</div>
        </div>
        <div class="summary-stats">
            <span class="stat-pill stat-expiring">Expiring Soon: <span id="stat-exp-cnt">0</span></span>
            <span class="stat-pill stat-active">Active: <span id="stat-act-cnt">0</span></span>
            <span class="stat-pill stat-upcoming">Upcoming: <span id="stat-up-cnt">0</span></span>
            <span class="stat-pill stat-total">Showing <span id="stat-show-cnt">0</span> of <span id="stat-tot-cnt">0</span> jobs</span>
        </div>
    </header>

    <!-- Status Tabs -->
    <nav class="tabs" role="tablist">
        <button class="tab-btn active" role="tab" data-status="expiring" id="tab-expiring">
            Expiring Soon <span class="tab-badge" id="tbadge-expiring">0</span>
        </button>
        <button class="tab-btn" role="tab" data-status="active" id="tab-active">
            Active <span class="tab-badge" id="tbadge-active">0</span>
        </button>
        <button class="tab-btn" role="tab" data-status="upcoming" id="tab-upcoming">
            Upcoming <span class="tab-badge" id="tbadge-upcoming">0</span>
        </button>
        <button class="tab-btn" role="tab" data-status="unverified" id="tab-unverified">
            Unverified Dates <span class="tab-badge" id="tbadge-unverified">0</span>
        </button>
        <button class="tab-btn" role="tab" data-status="all" id="tab-all">
            All Records <span class="tab-badge" id="tbadge-all">0</span>
        </button>
    </nav>

    <!-- Sticky Filters Bar -->
    <div class="filters-bar">
        <div class="filter-row">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search organisation, post title, or keywords..." aria-label="Search jobs">
            </div>
            <select id="level-select" aria-label="Filter by level">
                <option value="">All Levels</option>
                <option value="psu">PSU / CPSE</option>
                <option value="central">Central Govt</option>
                <option value="state">State Govt</option>
                <option value="defence">Defence</option>
            </select>
            <select id="state-select" aria-label="Filter by state">
                <option value="">All States / UTs</option>
            </select>
            <select id="sector-select" aria-label="Filter by sector">
                <option value="">All Sectors</option>
            </select>
            <select id="gate-select" aria-label="Filter by GATE requirement">
                <option value="">GATE: Any</option>
                <option value="gate_only">GATE Required</option>
                <option value="no_gate">No GATE</option>
            </select>
            <select id="sort-select" aria-label="Sort order">
                <option value="closing_soon">Sort: Closing Soonest</option>
                <option value="newest">Sort: Newest First</option>
                <option value="vacancies">Sort: Most Vacancies</option>
            </select>
        </div>

        <!-- PSU Class Chips -->
        <div class="chips-group" id="psu-chips">
            <span class="chip-label">PSU Class:</span>
            <span class="chip active" data-psu="">All</span>
            <span class="chip" data-psu="maharatna">Maharatna</span>
            <span class="chip" data-psu="navratna">Navratna</span>
            <span class="chip" data-psu="miniratna">Miniratna</span>
            <span class="chip" data-psu="other_psu">Other PSU</span>
            <span class="chip" data-psu="non_psu">Non-PSU</span>
        </div>

        <!-- Branch Multi-select Chips -->
        <div class="chips-group" id="branch-chips">
            <span class="chip-label">Branch:</span>
            <span class="chip active" data-branch="ALL">ALL</span>
            <span class="chip" data-branch="CSE">CSE</span>
            <span class="chip" data-branch="IT">IT</span>
            <span class="chip" data-branch="ECE">ECE</span>
            <span class="chip" data-branch="EEE">EEE</span>
            <span class="chip" data-branch="ME">ME</span>
            <span class="chip" data-branch="CE">CE</span>
            <span class="chip" data-branch="CHE">CHE</span>
            <span class="chip" data-branch="INSTRU">INSTRU</span>
            <span class="chip" data-branch="MET">MET</span>
            <span class="chip" data-branch="MIN">MIN</span>
            <span class="chip" data-branch="AERO">AERO</span>
            <span class="chip" data-branch="MARINE">MARINE</span>
            <span class="chip" data-branch="OTHER">OTHER</span>
        </div>

        <div class="options-row">
            <label class="checkbox-label">
                <input type="checkbox" id="permanent-only-chk" checked>
                <span>Permanent posts only</span>
            </label>
            <label class="checkbox-label">
                <input type="checkbox" id="show-closed-chk">
                <span>Include closed / expired jobs</span>
            </label>
        </div>
    </div>

    <!-- Cards Container -->
    <main>
        <div class="cards-list" id="cards-container"></div>
        <div class="pagination-bar" id="pagination-bar" style="display:none;">
            <button class="btn-show-more" id="btn-show-more">Show More</button>
        </div>
    </main>
</div>

<!-- Raw Embedded Data -->
<script type="application/json" id="jobs-data">
__JOBS_JSON_DATA__
</script>

<script>
(function() {
    "use strict";

    // 1. Load Data
    var rawText = document.getElementById("jobs-data").textContent;
    var allJobs = [];
    try {
        allJobs = JSON.parse(rawText);
    } catch(e) {
        console.error("Failed to parse jobs JSON:", e);
    }

    // 2. Compute dynamic IST Today (Asia/Kolkata)
    function getTodayIST() {
        try {
            var s = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
            if (s && s.length === 10) return s;
        } catch(e) {}
        return new Date().toISOString().substring(0, 10);
    }
    var todayIST = getTodayIST();

    // 3. Dynamic Status Calculation in JavaScript
    // Statuses: expiring, active, upcoming, unverified, closed
    function computeStatus(job) {
        if (job.needs_review || !job.end_date) {
            return "unverified";
        }
        if (job.end_date < todayIST) {
            return "closed";
        }
        if (job.start_date && job.start_date > todayIST) {
            return "upcoming";
        }
        // Calculate days left
        var dl = calcDaysLeft(job.end_date);
        if (dl !== null && dl <= 7) {
            return "expiring";
        }
        return "active";
    }

    function calcDaysLeft(endDateStr) {
        if (!endDateStr) return null;
        try {
            var d1 = new Date(todayIST + "T00:00:00");
            var d2 = new Date(endDateStr + "T00:00:00");
            var diff = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
            return diff;
        } catch(e) {
            return null;
        }
    }

    function formatDDMMYYYY(iso) {
        if (!iso || iso.length < 10) return "-";
        var parts = iso.substring(0, 10).split("-");
        if (parts.length === 3) {
            return parts[2] + "/" + parts[1] + "/" + parts[0];
        }
        return iso;
    }

    // Assign computed statuses
    for (var i = 0; i < allJobs.length; i++) {
        var j = allJobs[i];
        j._status = computeStatus(j);
        j._daysLeft = calcDaysLeft(j.end_date);
    }

    // 4. Populate Dropdowns (States, Sectors)
    var stateSelect = document.getElementById("state-select");
    var sectorSelect = document.getElementById("sector-select");
    var statesSet = {};
    var sectorsSet = {};

    for (var i = 0; i < allJobs.length; i++) {
        var j = allJobs[i];
        if (j.state) statesSet[j.state] = true;
        if (j.sector) sectorsSet[j.sector] = true;
    }

    Object.keys(statesSet).sort().forEach(function(st) {
        var opt = document.createElement("option");
        opt.value = st;
        opt.textContent = st;
        stateSelect.appendChild(opt);
    });

    Object.keys(sectorsSet).sort().forEach(function(sec) {
        var opt = document.createElement("option");
        opt.value = sec;
        opt.textContent = sec.replace(/_/g, " ").replace(/\\b\\w/g, function(l){return l.toUpperCase()});
        sectorSelect.appendChild(opt);
    });

    // 5. State Management
    var activeTab = "expiring";
    var selectedPSUClass = "";
    var selectedBranches = { "ALL": true };
    var renderedCount = 0;
    var CHUNK_SIZE = 50;
    var filteredJobs = [];

    // Count badges
    function updateCounts() {
        var exp = 0, act = 0, upc = 0, unv = 0, tot = 0;
        for (var i = 0; i < allJobs.length; i++) {
            var st = allJobs[i]._status;
            if (st === "expiring") exp++;
            else if (st === "active") act++;
            else if (st === "upcoming") upc++;
            else if (st === "unverified") unv++;
            if (st !== "closed") tot++;
        }
        document.getElementById("stat-exp-cnt").textContent = exp;
        document.getElementById("stat-act-cnt").textContent = act;
        document.getElementById("stat-up-cnt").textContent = upc;
        document.getElementById("stat-tot-cnt").textContent = allJobs.length;

        document.getElementById("tbadge-expiring").textContent = exp;
        document.getElementById("tbadge-active").textContent = act;
        document.getElementById("tbadge-upcoming").textContent = upc;
        document.getElementById("tbadge-unverified").textContent = unv;
        document.getElementById("tbadge-all").textContent = allJobs.length;
    }
    updateCounts();

    // 6. Filtering & Sorting
    function applyFilters() {
        var searchQ = document.getElementById("search-input").value.trim().toLowerCase();
        var selLevel = document.getElementById("level-select").value.toLowerCase();
        var selState = document.getElementById("state-select").value.toLowerCase();
        var selSector = document.getElementById("sector-select").value.toLowerCase();
        var selGate = document.getElementById("gate-select").value;
        var sortMode = document.getElementById("sort-select").value;
        var permOnly = document.getElementById("permanent-only-chk").checked;
        var showClosed = document.getElementById("show-closed-chk").checked;

        filteredJobs = allJobs.filter(function(j) {
            // Tab filter
            if (activeTab === "expiring" && j._status !== "expiring") return false;
            if (activeTab === "active" && j._status !== "active") return false;
            if (activeTab === "upcoming" && j._status !== "upcoming") return false;
            if (activeTab === "unverified" && j._status !== "unverified") return false;
            if (activeTab === "all" && !showClosed && j._status === "closed") return false;

            // Closed filter
            if (!showClosed && activeTab !== "all" && j._status === "closed") return false;

            // Permanent only
            if (permOnly && j.employment_type && j.employment_type !== "permanent") return false;

            // Search
            if (searchQ) {
                var text = ((j.org || "") + " " + (j.post_title || "") + " " + (j.description || "") + " " + (j.psu_name || "")).toLowerCase();
                if (text.indexOf(searchQ) === -1) return false;
            }

            // Level
            if (selLevel && (j.level || "").toLowerCase() !== selLevel) return false;

            // State
            if (selState && (j.state || "").toLowerCase() !== selState) return false;

            // Sector
            if (selSector && (j.sector || "").toLowerCase() !== selSector) return false;

            // GATE
            if (selGate === "gate_only" && !j.gate_required) return false;
            if (selGate === "no_gate" && j.gate_required) return false;

            // PSU Class
            if (selectedPSUClass) {
                var pcls = (j.psu_class || "").toLowerCase();
                if (selectedPSUClass === "miniratna") {
                    if (pcls !== "miniratna_1" && pcls !== "miniratna_2") return false;
                } else if (selectedPSUClass === "other_psu") {
                    if ((j.level || "").toLowerCase() !== "psu" || (pcls && pcls !== "none")) return false;
                } else if (selectedPSUClass === "non_psu") {
                    if ((j.level || "").toLowerCase() === "psu") return false;
                } else {
                    if (pcls !== selectedPSUClass) return false;
                }
            }

            // Branch chips
            if (!selectedBranches["ALL"]) {
                var jBranches = (j.branches || []).map(function(b){ return b.toUpperCase(); });
                var matchBranch = false;
                for (var b in selectedBranches) {
                    if (selectedBranches[b] && (jBranches.indexOf(b) !== -1 || jBranches.indexOf("ALL") !== -1)) {
                        matchBranch = true;
                        break;
                    }
                }
                if (!matchBranch) return false;
            }

            return true;
        });

        // Sorting
        filteredJobs.sort(function(a, b) {
            if (sortMode === "closing_soon") {
                var d1 = a._daysLeft === null ? 99999 : a._daysLeft;
                var d2 = b._daysLeft === null ? 99999 : b._daysLeft;
                if (d1 < 0) d1 = 999999;
                if (d2 < 0) d2 = 999999;
                return d1 - d2;
            } else if (sortMode === "newest") {
                return (b.start_date || "").localeCompare(a.start_date || "");
            } else if (sortMode === "vacancies") {
                return (b.vacancies || 0) - (a.vacancies || 0);
            }
            return 0;
        });

        renderedCount = 0;
        renderCards(false);
    }

    // 7. Render Cards to DOM
    var container = document.getElementById("cards-container");
    var showMoreBtn = document.getElementById("btn-show-more");
    var paginationBar = document.getElementById("pagination-bar");

    function renderCards(append) {
        if (!append) {
            container.textContent = "";
        }

        document.getElementById("stat-show-cnt").textContent = filteredJobs.length;

        if (filteredJobs.length === 0) {
            var empty = document.createElement("div");
            empty.className = "no-jobs";
            empty.textContent = "No recruitment notices match the active filters or tab.";
            container.appendChild(empty);
            paginationBar.style.display = "none";
            return;
        }

        var toRender = filteredJobs.slice(renderedCount, renderedCount + CHUNK_SIZE);
        for (var i = 0; i < toRender.length; i++) {
            var card = createCardElement(toRender[i]);
            container.appendChild(card);
        }
        renderedCount += toRender.length;

        if (renderedCount < filteredJobs.length) {
            paginationBar.style.display = "block";
            showMoreBtn.textContent = "Show More (Showing " + renderedCount + " of " + filteredJobs.length + ")";
        } else {
            paginationBar.style.display = "none";
        }
    }

    function createCardElement(job) {
        var card = document.createElement("article");
        card.className = "card";

        // Header
        var header = document.createElement("div");
        header.className = "card-header";

        var orgWrap = document.createElement("div");
        orgWrap.className = "org-wrap";

        var orgSpan = document.createElement("span");
        orgSpan.className = "org-name";
        orgSpan.textContent = job.org || "Government Recruiter";
        orgWrap.appendChild(orgSpan);

        if (job.psu_class && job.psu_class !== "none") {
            var psuBadge = document.createElement("span");
            psuBadge.className = "ratna-badge";
            var label = job.psu_class.replace("_", "-").toUpperCase();
            psuBadge.textContent = label;
            orgWrap.appendChild(psuBadge);
        }
        header.appendChild(orgWrap);

        // Days left badge
        var daysChip = document.createElement("span");
        daysChip.className = "days-chip";
        var dl = job._daysLeft;
        if (job._status === "unverified") {
            daysChip.className += " days-orange";
            daysChip.textContent = "Dates Unverified";
        } else if (job._status === "closed") {
            daysChip.className += " days-gray";
            daysChip.textContent = "Closed";
        } else if (job._status === "upcoming") {
            daysChip.className += " days-blue";
            daysChip.textContent = "Upcoming";
        } else if (dl !== null) {
            if (dl <= 3) {
                daysChip.className += " days-red";
                daysChip.textContent = dl + "d left (Closing Soon)";
            } else if (dl <= 7) {
                daysChip.className += " days-orange";
                daysChip.textContent = dl + "d left";
            } else {
                daysChip.className += " days-green";
                daysChip.textContent = dl + "d left";
            }
        }
        header.appendChild(daysChip);
        card.appendChild(header);

        // Title
        var titleH3 = document.createElement("h3");
        titleH3.className = "post-title";
        titleH3.textContent = job.post_title;
        card.appendChild(titleH3);

        // Tags
        var tagsRow = document.createElement("div");
        tagsRow.className = "tags-row";

        if (job.branches && job.branches.length > 0) {
            var bTag = document.createElement("span");
            bTag.className = "tag tag-branch";
            bTag.textContent = "Branches: " + job.branches.join(", ");
            tagsRow.appendChild(bTag);
        }

        var gateTag = document.createElement("span");
        gateTag.className = "tag tag-gate";
        gateTag.textContent = job.gate_required ? "GATE Required" : "No GATE Required";
        tagsRow.appendChild(gateTag);

        if (job.vacancies) {
            var vacTag = document.createElement("span");
            vacTag.className = "tag tag-vacancies";
            vacTag.textContent = job.vacancies + " Vacancies";
            tagsRow.appendChild(vacTag);
        }

        if (job.employment_type) {
            var empTag = document.createElement("span");
            empTag.className = "tag";
            empTag.textContent = job.employment_type.charAt(0).toUpperCase() + job.employment_type.slice(1);
            tagsRow.appendChild(empTag);
        }
        card.appendChild(tagsRow);

        // Additional requirements
        if (job.additional_requirements && job.additional_requirements.length > 0) {
            var reqList = document.createElement("ul");
            reqList.className = "requirements-list";
            for (var r = 0; r < job.additional_requirements.length; r++) {
                var li = document.createElement("li");
                li.textContent = job.additional_requirements[r];
                reqList.appendChild(li);
            }
            card.appendChild(reqList);
        }

        // Meta Grid
        var metaGrid = document.createElement("div");
        metaGrid.className = "meta-grid";

        var pScale = document.createElement("span");
        pScale.innerHTML = "<strong>Pay Scale:</strong> ";
        pScale.appendChild(document.createTextNode(job.pay_level_or_scale || "As per Govt rules"));
        metaGrid.appendChild(pScale);

        var sDate = document.createElement("span");
        sDate.innerHTML = "<strong>Start Date:</strong> ";
        sDate.appendChild(document.createTextNode(formatDDMMYYYY(job.start_date)));
        metaGrid.appendChild(sDate);

        var eDate = document.createElement("span");
        eDate.innerHTML = "<strong>Last Date:</strong> ";
        eDate.appendChild(document.createTextNode(formatDDMMYYYY(job.end_date)));
        metaGrid.appendChild(eDate);

        if (job.notification_no) {
            var nNo = document.createElement("span");
            nNo.innerHTML = "<strong>Advt No:</strong> ";
            nNo.appendChild(document.createTextNode(job.notification_no));
            metaGrid.appendChild(nNo);
        }
        card.appendChild(metaGrid);

        // Card Actions
        var actions = document.createElement("div");
        actions.className = "card-actions";

        var btnGroup = document.createElement("div");
        btnGroup.className = "btn-group";

        if (job.source_url && (job.source_url.indexOf("http://") === 0 || job.source_url.indexOf("https://") === 0)) {
            var aPortal = document.createElement("a");
            aPortal.className = "btn btn-primary";
            aPortal.href = job.source_url;
            aPortal.target = "_blank";
            aPortal.rel = "noopener noreferrer";
            aPortal.textContent = "Official Portal ↗";
            btnGroup.appendChild(aPortal);
        }

        if (job.notice_url && (job.notice_url.indexOf("http://") === 0 || job.notice_url.indexOf("https://") === 0)) {
            var aPdf = document.createElement("a");
            aPdf.className = "btn btn-secondary";
            aPdf.href = job.notice_url;
            aPdf.target = "_blank";
            aPdf.rel = "noopener noreferrer";
            aPdf.textContent = "Official Notice (PDF) 📄";
            btnGroup.appendChild(aPdf);
        }
        actions.appendChild(btnGroup);

        var note = document.createElement("span");
        note.className = "official-note";
        note.textContent = "Always verify on the official portal before applying.";
        actions.appendChild(note);

        card.appendChild(actions);
        return card;
    }

    // 8. Event Listeners
    // Status Tabs
    var tabBtns = document.querySelectorAll(".tab-btn");
    for (var i = 0; i < tabBtns.length; i++) {
        tabBtns[i].addEventListener("click", function() {
            for (var t = 0; t < tabBtns.length; t++) tabBtns[t].classList.remove("active");
            this.classList.add("active");
            activeTab = this.getAttribute("data-status");
            applyFilters();
        });
    }

    // Inputs
    document.getElementById("search-input").addEventListener("input", applyFilters);
    document.getElementById("level-select").addEventListener("change", applyFilters);
    document.getElementById("state-select").addEventListener("change", applyFilters);
    document.getElementById("sector-select").addEventListener("change", applyFilters);
    document.getElementById("gate-select").addEventListener("change", applyFilters);
    document.getElementById("sort-select").addEventListener("change", applyFilters);
    document.getElementById("permanent-only-chk").addEventListener("change", applyFilters);
    document.getElementById("show-closed-chk").addEventListener("change", applyFilters);

    // PSU Chips
    var psuChips = document.querySelectorAll("#psu-chips .chip");
    for (var i = 0; i < psuChips.length; i++) {
        psuChips[i].addEventListener("click", function() {
            for (var c = 0; c < psuChips.length; c++) psuChips[c].classList.remove("active");
            this.classList.add("active");
            selectedPSUClass = this.getAttribute("data-psu");
            applyFilters();
        });
    }

    // Branch Chips (Multi-select)
    var branchChips = document.querySelectorAll("#branch-chips .chip");
    for (var i = 0; i < branchChips.length; i++) {
        branchChips[i].addEventListener("click", function() {
            var b = this.getAttribute("data-branch");
            if (b === "ALL") {
                selectedBranches = { "ALL": true };
                for (var c = 0; c < branchChips.length; c++) branchChips[c].classList.remove("active");
                this.classList.add("active");
            } else {
                delete selectedBranches["ALL"];
                document.querySelector('#branch-chips [data-branch="ALL"]').classList.remove("active");
                if (selectedBranches[b]) {
                    delete selectedBranches[b];
                    this.classList.remove("active");
                } else {
                    selectedBranches[b] = true;
                    this.classList.add("active");
                }
                // If none selected, default to ALL
                if (Object.keys(selectedBranches).length === 0) {
                    selectedBranches["ALL"] = true;
                    document.querySelector('#branch-chips [data-branch="ALL"]').classList.add("active");
                }
            }
            applyFilters();
        });
    }

    // Show more button
    showMoreBtn.addEventListener("click", function() {
        renderCards(true);
    });

    // Initial render
    applyFilters();
})();
</script>
</body>
</html>
"""

def export_csv(jobs: List[Job], output_path: str = "data/jobs.csv", include_closed: bool = False):
    """
    Export jobs to CSV format.
    Excludes closed jobs by default unless include_closed=True.
    Dates are formatted as DD/MM/YYYY.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    today = get_ist_today()

    active_jobs = []
    for job in jobs:
        st = compute_job_status(job, today=today)
        if not include_closed and st == JobStatus.CLOSED:
            continue
        active_jobs.append(job)

    # Sort active jobs: expiring -> active -> upcoming
    active_jobs.sort(key=lambda j: job_sort_key(j, today=today))

    fieldnames = [
        "id", "org", "post_title", "notification_no", "level", "state", "sector",
        "category", "psu_name", "psu_class", "ministry",
        "qualification_type", "btech_eligible", "branches", "gate_required",
        "vacancies", "pay_level_or_scale", "start_date", "end_date",
        "status", "days_left", "source_url", "notice_url"
    ]

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in active_jobs:
            st = compute_job_status(job, today=today)
            dl = days_left(job, today=today)
            row = {
                "id": job.id,
                "org": job.org,
                "post_title": job.post_title,
                "notification_no": job.notification_no or "",
                "level": job.level.value,
                "state": job.state or "",
                "sector": job.sector,
                "category": job.category or "",
                "psu_name": job.psu_name or "",
                "psu_class": job.psu_class or "",
                "ministry": job.ministry or "",
                "qualification_type": job.qualification_type.value,
                "btech_eligible": "Yes" if job.btech_eligible else "No",
                "branches": ", ".join([b.value for b in job.branches]) if job.branches else "",
                "gate_required": "Yes" if job.gate_required else ("No" if job.gate_required is False else ""),
                "vacancies": job.vacancies if job.vacancies is not None else "",
                "pay_level_or_scale": job.pay_level_or_scale or "",
                "start_date": fmt_date(job.start_date),
                "end_date": fmt_date(job.end_date),
                "status": st.value,
                "days_left": dl if dl is not None else "",
                "source_url": job.source_url,
                "notice_url": job.notice_url or "",
            }
            writer.writerow(row)

def export_html(jobs: List[Job], output_path: str = "data/jobs.html", include_closed: bool = False):
    """
    Export jobs to self-contained interactive offline HTML.
    Zero external requests. Status dynamically computed in browser from IST dates.
    HTML-safe escaping applied to all embedded JSON data.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    today = get_ist_today()

    export_records = []
    for job in jobs:
        st = compute_job_status(job, today=today)
        if not include_closed and st == JobStatus.CLOSED:
            continue
        d = job.model_dump()
        d["branches"] = [b.value for b in job.branches] if job.branches else []
        d["start_date_display"] = fmt_date(job.start_date)
        d["end_date_display"] = fmt_date(job.end_date)
        export_records.append(d)

    # Sort records: expiring first, then active, then upcoming
    export_records.sort(key=lambda d: job_sort_key(Job(**{k: v for k, v in d.items() if k not in ["_status", "_daysLeft"]}), today=today))

    # Serialize JSON with XSS safety (< and > escaped)
    raw_json = json.dumps(export_records, ensure_ascii=False)
    safe_json = raw_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    updated_str = datetime.now(IST).strftime("%d/%m/%Y %H:%M IST")

    html_content = HTML_TEMPLATE.replace("__UPDATED_AT__", updated_str).replace("__JOBS_JSON_DATA__", safe_json)
    path.write_text(html_content, encoding="utf-8")
