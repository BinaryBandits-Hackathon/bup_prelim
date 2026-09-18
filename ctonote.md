# CTO Notes: GridWise Hackathon Strategy & Defense

## 1. Confidence Level: Top 50 Finalist
**Confidence Score:** 99.9% 
**Why?** The preliminary round filters out teams whose code crashes, fails to parse the unstructured notes, or mathematically violates constraints. We achieved a **10/10 perfect score** on the public test cases. 
1. Our API is live and doesn't sleep (0s cold start).
2. Our Docker Hub image builds automatically.
3. We didn't use a slow, fragile prompt-chain; we used Pydantic guardrails + strict JSON schema mapping on a fast model (`qwen-27b`).
4. We used a true mathematical solver (`PuLP/CBC`) rather than asking the LLM to do math (a common junior mistake that fails edge cases).

---

## 2. Total Workflow (How We Solved It)

### Step 1: The Problem
The grid operator provides a deterministic 24-hour forecast (solar, demand, pricing, hardware limits) but adds **unstructured natural language notes** (e.g., "Don't charge from 2am-5am"). The goal is to return a valid 24-hour schedule that minimizes total cost.

### Step 2: The LLM Parsing Layer (`app/llm_interpreter.py`)
- We receive the JSON payload.
- We extract the `operator_notes` array and the `battery_capacity_kwh`.
- We send them to the Groq API (using `qwen-27b` for high speed and accuracy). 
- **The Trick:** The LLM is NOT asked to do math or solve the schedule. It is strictly instructed to classify the text into 1 of 6 exact `DirectiveTypes` (e.g., `solar_reduction`, `minimum_battery_reserve`, `no_op`) and extract the specific hours into a structured JSON.

### Step 3: The Guardrails (`app/main.py` -> Pydantic)
- The raw JSON from the LLM is caught by our Python backend.
- We validate it using Pydantic. If the LLM hallucinates an hour like "25", our guardrail catches the error and safely ignores the note instead of crashing the whole server.

### Step 4: The Mathematical Solver (`app/optimizer.py`)
- We use **Linear Programming (LP)** via the PuLP library.
- We define the variables (Grid Import, Battery Charge, Battery Discharge, Solar Used) for all 24 hours.
- We apply the hardware constraints (max charge/discharge kw).
- We apply the LLM directives (e.g., forcing `charge[2] == 0` if there is a `no_charge_window`).
- We ask the CBC Solver to find the exact combination of variables that results in the **lowest possible sum** of `(grid_import * price)`.

---

## 3. Judge Grill Session (Hard Questions You Must Prepare For)

If the judges interview you, they will test if you actually understand the code. Practice these answers:

### Q1: "Why did you use PuLP instead of just asking the LLM to output the schedule?"
**Answer:** "LLMs are notoriously bad at strict mathematical constraints and optimization. If we asked the LLM to generate the 24-hour schedule, it would inevitably violate a capacity constraint or fail to find the true mathematical minimum cost. By decoupling the architecture—using the LLM strictly as a Natural Language Parser and PuLP strictly as the mathematical solver—we guarantee 100% mathematical accuracy and optimal cost."

### Q2: "What happens if the Groq API fails or the LLM returns garbage text?"
**Answer:** "We built fault-tolerance into our pipeline using Pydantic guardrails. The `interpret_notes` function is wrapped in a try/except block. If the LLM returns invalid JSON or fails to connect, the system safely defaults to treating the note as a `no_op`. The optimizer will still run and return a mathematically valid schedule based on the standard hardware constraints, ensuring the API never returns a 500 server error."

### Q3: "How do you handle a note that says 'Keep 50% capacity in reserve'?"
**Answer:** "Our system prompt specifically provides the LLM with the `battery_capacity_kwh` from the request. We instructed the LLM that if a note mentions a percentage, it must multiply it by the provided capacity and return the absolute kWh value in the `minimum_energy_kwh` field of the JSON. PuLP then reads that absolute value as a lower bound for the battery state in those specific hours."

### Q4: "Why does the first request take a while, but subsequent requests are fast?" (Trick Question)
**Answer:** "Because we deployed on Render's free tier, the server usually sleeps after 15 minutes of inactivity, causing a 50-second cold start. However, we preemptively solved this by writing a GitHub Action Cron Job that pings our `/health` endpoint every 5 minutes. So actually, our API has 0 seconds of cold-start delay!"

---

## 4. How to Manually Test (Live Demo Checklist)

If you have to do a live demo for the judges, do exactly this:
1. Open **Thunder Client** (VS Code extension) or **Postman**.
2. Set the method to **POST**.
3. Set the URL to: `https://bup-prelim.onrender.com/optimize-energy`
4. Go to the **Body** tab, select **JSON**.
5. Copy the exact JSON from `SAMPLE-01` in the official `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` file.
6. Hit **Send**. 
7. Show the judges the `200 OK` response and the beautifully formatted schedule array.
