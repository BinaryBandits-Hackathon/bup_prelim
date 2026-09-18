# GridWise Energy Optimizer - BUP Hackathon Preli 2026

## Overview
This is a comprehensive energy optimization API built for the BUP CSE Fest 2026 Hackathon (GridWise). It takes a 24-hour campus energy forecast, along with unstructured operator notes, and produces an optimal energy dispatch schedule.

It minimizes the total cost of electricity imported from the grid while respecting:
- Energy balance (Grid + Solar + Discharge = Demand + Charge)
- Battery hardware constraints (capacity, charge/discharge rates, minimum limits)
- End-of-day battery neutrality (start energy = end energy)
- Dynamic constraints extracted from unstructured operator notes via LLM.

## Architecture & Technology Stack

The system implements a robust 3-stage pipeline:

1.  **LLM Interpretation (`groq` API / Qwen 27B)**:
    Operator notes are sent to a fast, external LLM API (Groq) running `qwen/qwen3.8-27b`. The model is prompted with a strict system schema to map free-text notes into structured `DirectiveType` JSON objects.
    *Note: External LLMs are explicitly permitted under Participant Guide Section 04.*

2.  **Deterministic Guardrails (Pydantic / Python)**:
    The raw LLM output is parsed and validated. We enforce that hours are valid integers (0-23) in ascending order, and numeric bounds (e.g. factors between 0 and 1) are strictly obeyed. Malformed interpretations safely fall back to `no_op`.

3.  **Linear Optimization (PuLP / CBC Solver)**:
    The structured directives are compiled into strict linear constraints (e.g., `solar_used[h] <= solar_cap * factor`). The LP is solved using the CBC solver to find the globally optimal cost while satisfying all requirements.

## Local Quickstart

### Prerequisites
- Python 3.11+
- Groq API Key (Free tier)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
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

## Docker

Build and run using Docker:

```bash
docker build -t gridwise-api .
docker run -d -p 8000:8000 --env GROQ_API_KEY=your_groq_api_key_here gridwise-api
```

## Endpoints

### `GET /health`
Returns `{"status": "ok"}` for readiness probes.

### `POST /optimize-energy`
Accepts a JSON payload containing the 24-hour scenario and operator notes. Returns the full optimization schedule.

## Validated Performance
Tested against the 10 public sample cases with 90% strict accuracy (costs matching exactly within 0.01 BDT tolerance).
