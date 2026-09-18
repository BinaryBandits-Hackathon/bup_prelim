"""LLM-based operator note interpreter with deterministic guardrails."""

import json
import re
from groq import Groq
from app.config import GROQ_API_KEY, GROQ_MODEL
from app.models import DirectiveInterpretation, DirectiveType

SYSTEM_PROMPT = """You are a campus energy system operator note interpreter for GridWise.

You will receive the total battery capacity and 1-3 operator notes. For EACH note, determine if it affects today's 24-hour energy schedule.

SUPPORTED DIRECTIVE TYPES (use EXACTLY these strings):
1. "solar_reduction" — Reduces usable solar during specific hours.
   structured_adjustment: {"hours": [list of integers 0-23], "factor": float}
   IMPORTANT: "factor" is the REMAINING usable fraction. An "80% reduction" means factor = 0.2. "Reduced to 25%" means factor = 0.25.

2. "minimum_battery_reserve" — Keep battery energy at or above a required level during specific hours.
   structured_adjustment: {"hours": [list of integers 0-23], "minimum_energy_kwh": float}
   IMPORTANT: If the note specifies a percentage (e.g., "50% of capacity"), you MUST calculate the absolute kWh value using the provided battery capacity. (e.g. 50% of 200 = 100.0).

3. "no_charge_window" — Battery charging is unavailable during specific hours.
   structured_adjustment: {"hours": [list of integers 0-23]}

4. "no_discharge_window" — Battery discharging is unavailable during specific hours.
   structured_adjustment: {"hours": [list of integers 0-23]}

5. "max_grid_window" — Grid import may not exceed a stated amount during specific hours.
   structured_adjustment: {"hours": [list of integers 0-23], "max_grid_kwh": float}

6. "no_op" — The note does NOT affect today's 24-hour energy schedule (e.g., irrelevant, future-dated, non-energy).
   structured_adjustment: null

TIME WINDOW RULES:
- Use 24-hour format integers (0-23).
- Windows are START-INCLUSIVE, END-EXCLUSIVE: "1 PM to 3 PM" = hours [13, 14]. "2 AM until 5 AM" = hours [2, 3, 4].
- Hours must be unique integers in ASCENDING order.

RESPONSE FORMAT — Return a JSON array with exactly one object per note, in order:
[
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {"hours": [13, 14], "factor": 0.25},
    "explanation": "Short explanation"
  },
  {
    "note_index": 1,
    "applies": false,
    "directive_type": "no_op",
    "structured_adjustment": null,
    "explanation": "This note does not affect today's energy schedule."
  }
]

RULES:
- Return ONLY the JSON array. No markdown, no explanation outside the JSON.
- For no_op: applies MUST be false, structured_adjustment MUST be null.
- For all other types: applies MUST be true.
- Each note maps to EXACTLY one directive type.
- If a note is ambiguous but seems energy-related, pick the closest directive type.
- If a note is clearly not about today's energy operations, use no_op.
"""


def _call_llm(notes: list[str], battery_capacity_kwh: float) -> str:
    """Call Groq LLM to interpret operator notes."""
    client = Groq(api_key=GROQ_API_KEY)

    notes_text = f"Battery Capacity: {battery_capacity_kwh} kWh\n\n"
    for i, note in enumerate(notes):
        notes_text += f"Note {i}: \"{note}\"\n"

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Interpret these operator notes:\n\n{notes_text}"}
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    return response.choices[0].message.content


def _extract_json_array(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, handling various formats."""
    raw = raw.strip()

    # Remove markdown code fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    parsed = json.loads(raw)

    # Handle case where LLM wraps array in an object
    if isinstance(parsed, dict):
        # Look for the array in common keys
        for key in ["interpretations", "directives", "notes", "results", "directive_interpretation"]:
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # If dict has numeric keys or single array value
        for v in parsed.values():
            if isinstance(v, list):
                return v
        # Wrap single dict as array
        return [parsed]

    if isinstance(parsed, list):
        return parsed

    return []


def _validate_hours(hours) -> list[int]:
    """Validate and normalize hours list."""
    if not isinstance(hours, list):
        return []
    validated = []
    for h in hours:
        h_int = int(h)
        if 0 <= h_int <= 23 and h_int not in validated:
            validated.append(h_int)
    return sorted(validated)


def _guardrail(raw_interpretations: list[dict], num_notes: int) -> list[DirectiveInterpretation]:
    """Apply deterministic guardrails to LLM output."""
    valid_types = {t.value for t in DirectiveType}
    results = []

    for i in range(num_notes):
        # Find the interpretation for this note index
        interp = None
        for item in raw_interpretations:
            idx = item.get("note_index", -1)
            if idx == i:
                interp = item
                break

        # If no interpretation found for this note, default to no_op
        if interp is None:
            # Try positional fallback
            if i < len(raw_interpretations):
                interp = raw_interpretations[i]
                interp["note_index"] = i
            else:
                results.append(DirectiveInterpretation(
                    note_index=i,
                    applies=False,
                    directive_type=DirectiveType.NO_OP,
                    structured_adjustment=None,
                    explanation="Unable to interpret this note; treated as not applicable."
                ))
                continue

        # Validate directive_type
        dtype = interp.get("directive_type", "no_op")
        if dtype not in valid_types:
            dtype = "no_op"

        explanation = interp.get("explanation", "Interpreted by LLM.")

        # Handle no_op
        if dtype == "no_op":
            results.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation=explanation
            ))
            continue

        # Validate structured_adjustment
        adj = interp.get("structured_adjustment", {})
        if not isinstance(adj, dict):
            adj = {}

        # Validate hours field (required for all non-no_op directives)
        hours = _validate_hours(adj.get("hours", []))
        if not hours:
            # No valid hours — fall back to no_op
            results.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation=f"Guardrail: no valid hours extracted. Original: {explanation}"
            ))
            continue

        # Build validated structured_adjustment based on directive type
        validated_adj = {"hours": hours}

        if dtype == "solar_reduction":
            factor = adj.get("factor", 1.0)
            try:
                factor = float(factor)
            except (TypeError, ValueError):
                factor = 1.0
            factor = max(0.0, min(1.0, factor))
            validated_adj["factor"] = factor

        elif dtype == "minimum_battery_reserve":
            reserve = adj.get("minimum_energy_kwh", 0)
            try:
                reserve = float(reserve)
            except (TypeError, ValueError):
                reserve = 0
            validated_adj["minimum_energy_kwh"] = max(0.0, reserve)

        elif dtype == "max_grid_window":
            max_grid = adj.get("max_grid_kwh", 0)
            try:
                max_grid = float(max_grid)
            except (TypeError, ValueError):
                max_grid = 0
            validated_adj["max_grid_kwh"] = max(0.0, max_grid)

        # no_charge_window and no_discharge_window only need hours

        results.append(DirectiveInterpretation(
            note_index=i,
            applies=True,
            directive_type=DirectiveType(dtype),
            structured_adjustment=validated_adj,
            explanation=explanation
        ))

    return results


def interpret_notes(notes: list[str], battery_capacity_kwh: float) -> list[DirectiveInterpretation]:
    """Full pipeline: LLM call → parse → guardrail → validated directives."""
    try:
        raw_text = _call_llm(notes, battery_capacity_kwh)
        raw_list = _extract_json_array(raw_text)
        return _guardrail(raw_list, len(notes))
    except Exception as e:
        # Safe failure: return no_op for all notes
        print(f"LLM interpretation error: {e}")
        return [
            DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation=f"Fallback: LLM unavailable. Error: {type(e).__name__}"
            )
            for i in range(len(notes))
        ]
