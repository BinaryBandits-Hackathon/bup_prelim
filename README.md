# GridWise Energy Optimizer - BUP Hackathon Preli 2026

## Overview
A production-grade energy optimization API built for the BUP CSE Fest 2026 Hackathon (GridWise). It takes a 24-hour campus energy forecast along with unstructured operator notes, and produces an optimal energy dispatch schedule.

It minimizes the total cost of electricity imported from the grid while respecting:
- Energy balance (Grid + Solar + Discharge = Demand + Charge)
- Battery hardware constraints (capacity, charge/discharge rates, minimum limits)
- End-of-day battery neutrality (start energy = end energy)
- Dynamic constraints extracted from unstructured operator notes via LLM

## Architecture & Technology Stack

The system implements a robust 3-stage pipeline:

1.  **LLM Interpretation (`groq` API / Qwen 27B)**:
    Operator notes are sent to a fast, external LLM API (Groq) running `qwen/qwen3.8-27b`. The model is prompted with a strict system schema to map free-text notes into structured `DirectiveType` JSON objects.
    *Note: External LLMs are explicitly permitted under Participant Guide Section 04.*

2.  **Deterministic Guardrails (Pydantic / Python)**:
    The raw LLM output is parsed and validated. We enforce that hours are valid integers (0-23) in ascending order, and numeric bounds (e.g. factors between 0 and 1) are strictly obeyed. Malformed interpretations safely fall back to `no_op`.

3.  **Linear Optimization (PuLP / CBC Solver)**:
    The structured directives are compiled into strict linear constraints (e.g., `solar_used[h] <= solar_cap * factor`). The LP is solved using the CBC solver to find the globally optimal cost while satisfying all requirements.

## Fault Tolerance & Reliability

The system is engineered to **never breach the 30-second response deadline**:

- **Multi-Key API Rotation:** Multiple Groq API keys are rotated with instant failover (`max_retries=0`). If one key is rate-limited or stalls, the next key is tried immediately.
- **Hard 25-Second Timeout:** The Groq client enforces a strict `timeout=25.0` on every LLM call, leaving a 5-second safety margin for the optimizer to run.
- **Graceful Degradation:** If all LLM keys fail or timeout, the endpoint catches the exception and falls back to a valid baseline schedule using only hardware constraints (no directives). The API **never returns a 5xx error** for a valid request.
- **Keep-Alive Cron:** A GitHub Actions workflow pings the `/health` endpoint every 5 minutes, preventing Render free-tier cold starts.

## Local Quickstart

### Prerequisites
- Python 3.11+
- Groq API Key (Free tier)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/BinaryBandits-Hackathon/bup_prelim.git
   cd bup_prelim
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure Environment Variables:
   Create a `.env` file in the root directory:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   PORT=8000
   ```

4. Run the API:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Docker (For Judges)

Due to CI environment limitations, the Docker image is not hosted on a public registry. Judges can build and run the image locally from the source code:

```bash
docker build -t gridwise-api .
docker run -d -p 8000:8000 --env GROQ_API_KEY=your_groq_api_key_here gridwise-api
```

## Endpoints

### `GET /health`
Returns `{"status": "ok"}` for readiness probes.

### `POST /optimize-energy`
Accepts a JSON payload containing the 24-hour scenario and operator notes. Returns the full optimization schedule.

## Public-Sample Test Command

You can verify the API is working locally (or against the live Render URL) using the following `curl` command for **SAMPLE-01**:

```bash
curl -X 'POST' \
  'https://bup-prelim.onrender.com/optimize-energy' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "scenario_id": "SAMPLE-01",
  "operator_notes": ["Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast."],
  "hours": [{"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6}, {"hour": 1, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 6}, {"hour": 2, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}, {"hour": 3, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}, {"hour": 4, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}, {"hour": 5, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6}, {"hour": 6, "demand_kwh": 110, "solar_kwh": 5, "tariff_bdt_per_kwh": 8}, {"hour": 7, "demand_kwh": 130, "solar_kwh": 20, "tariff_bdt_per_kwh": 10}, {"hour": 8, "demand_kwh": 150, "solar_kwh": 50, "tariff_bdt_per_kwh": 12}, {"hour": 9, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14}, {"hour": 10, "demand_kwh": 175, "solar_kwh": 130, "tariff_bdt_per_kwh": 16}, {"hour": 11, "demand_kwh": 180, "solar_kwh": 160, "tariff_bdt_per_kwh": 16}, {"hour": 12, "demand_kwh": 185, "solar_kwh": 180, "tariff_bdt_per_kwh": 15}, {"hour": 13, "demand_kwh": 180, "solar_kwh": 170, "tariff_bdt_per_kwh": 14}, {"hour": 14, "demand_kwh": 170, "solar_kwh": 140, "tariff_bdt_per_kwh": 13}, {"hour": 15, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14}, {"hour": 16, "demand_kwh": 170, "solar_kwh": 45, "tariff_bdt_per_kwh": 18}, {"hour": 17, "demand_kwh": 185, "solar_kwh": 10, "tariff_bdt_per_kwh": 22}, {"hour": 18, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 28}, {"hour": 19, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 30}, {"hour": 20, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 26}, {"hour": 21, "demand_kwh": 175, "solar_kwh": 0, "tariff_bdt_per_kwh": 18}, {"hour": 22, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 10}, {"hour": 23, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}],
  "battery": {"capacity_kwh": 220, "initial_energy_kwh": 110, "minimum_energy_kwh": 40, "max_charge_kwh_per_hour": 50, "max_discharge_kwh_per_hour": 50}
}'
```

## Dependencies & Secret Handling

- **LLM Provider:** This API relies on the external Groq API (`qwen-27b`) for note interpretation.
- **Secrets:** API keys are strictly handled via environment variables (e.g. `GROQ_API_KEY`). **No secrets are ever hardcoded or committed to version control.** A `.dockerignore` file ensures `.env` is excluded from container builds.
- **Error Handling:** The API handles validation and solver errors safely. In the event of an unprocessable operator note, the system safely falls back to a `no_op` directive. If the entire payload is malformed, a descriptive `422` error is returned. No internal `500` errors are exposed.

## Validated Performance

Tested against all 10 public sample cases with **100% strict accuracy** — costs, grid totals, peak values, directives, and physical constraints all match exactly within 0.01 BDT tolerance.

## Team

- **Tijul Kabir Toha** — Team Binary Bandits
- **Event:** BUP CSE Fest 2026 — LLM-Assisted Smart Campus Energy Optimization
