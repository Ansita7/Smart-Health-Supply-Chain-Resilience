"""PulseGrid API.  pip install fastapi uvicorn
Run: uvicorn pulsegrid_api:app --reload   then open http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pulsegrid_core as core

app = FastAPI(title="PulseGrid API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
CENTRES = core.make_centres(500)


def check(med):
    if med not in core.MEDICINES:
        raise HTTPException(404, f"Unknown medicine. Use one of {list(core.MEDICINES)}")


@app.get("/centres")
def centres(medicine: str = "ORS sachets", outbreak: int = Query(0, ge=0, le=100)):
    check(medicine)
    return [{"id": c["id"], "district": c["district"], "x": round(c["x"]), "y": round(c["y"]),
             "stock": round(c["stock"][medicine]),
             "days_left": round(core.days_left(c, medicine, outbreak), 1),
             "status": core.status(c, medicine, outbreak)} for c in CENTRES]


@app.get("/plan")
def plan(medicine: str = "ORS sachets", outbreak: int = Query(0, ge=0, le=100)):
    check(medicine)
    moves = core.plan(CENTRES, medicine, outbreak)
    return {"count": len(moves), "moves": moves}


class Approval(BaseModel):
    medicine: str
    outbreak: int = 0


@app.post("/approve")
def approve(a: Approval):
    """Officer approves the current plan: stock levels update."""
    check(a.medicine)
    moves = core.plan(CENTRES, a.medicine, a.outbreak)
    core.apply_moves(CENTRES, moves)
    return {"applied": len(moves)}
