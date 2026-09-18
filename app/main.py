"""FastAPI application for GridWise energy optimization."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app.models import OptimizeRequest, OptimizeResponse
from app.llm_interpreter import interpret_notes
from app.optimizer import optimize_energy
from app.config import PORT

app = FastAPI(
    title="GridWise Energy Optimizer",
    description="BUP CSE Fest 2026 — LLM-Assisted Smart Campus Energy Optimization",
    version="1.0.0"
)


@app.get("/health")
async def health():
    """Readiness endpoint for the judging harness."""
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy_endpoint(request: OptimizeRequest):
    """
    Main endpoint: interpret operator notes via LLM, apply directives,
    optimize 24-hour energy schedule, and return the complete response.
    """
    try:
        # Validate hours cover 0-23
        hour_set = {h.hour for h in request.hours}
        if hour_set != set(range(24)):
            raise HTTPException(
                status_code=400,
                detail="hours must contain exactly 24 unique entries for hours 0 through 23."
            )

        # Step 1: LLM interpretation with guardrails
        directives = interpret_notes(request.operator_notes, request.battery.capacity_kwh)

        # Step 2: Optimize energy schedule with directives applied
        result = optimize_energy(request, directives)

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {type(e).__name__}"
        )


@app.exception_handler(422)
async def validation_error_handler(request, exc):
    """Handle Pydantic validation errors gracefully."""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc.detail) if hasattr(exc, 'detail') else "Validation error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
