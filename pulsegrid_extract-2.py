"""PulseGrid field-report extraction.

A health worker sends a WhatsApp voice note or a photo of the medicine shelf.
Gemini turns it into structured stock, staff and bed numbers.
Low-confidence readings are flagged for a human instead of being trusted.

Setup:  pip install fastapi uvicorn python-multipart google-genai pydantic
Run:    GEMINI_API_KEY=... uvicorn pulsegrid_extract:app --reload
Note:   set GEMINI_MODEL to a current multimodal Gemini model from Google's docs.
        I could not test this here, so run it once with a sample before the demo.
"""
import os
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
app = FastAPI(title="PulseGrid field reports")

MEDICINES = ["ORS sachets", "Paracetamol", "Amoxicillin", "Antimalarial"]


class StockLine(BaseModel):
    medicine: Literal["ORS sachets", "Paracetamol", "Amoxicillin", "Antimalarial"]
    quantity: int = Field(ge=0, description="Units currently in stock")
    confidence: float = Field(ge=0, le=1, description="How sure you are of this number")


class Report(BaseModel):
    stock: list[StockLine]
    staff_absent: Optional[int] = Field(default=None, ge=0)
    beds_free: Optional[int] = Field(default=None, ge=0)
    language: str = Field(description="Language the report was given in")
    transcript_summary: str


PROMPT = f"""You read field reports from a primary health centre in India.
The input is a voice note (any Indian language) or a photo of a medicine shelf.
Extract only what is clearly stated or visible. Never guess a quantity.
Track only these medicines: {', '.join(MEDICINES)}.
Give each quantity a confidence from 0 to 1. Use a low value if the audio is
unclear, the label is hard to read, or the count is partly hidden."""

REVIEW_BELOW = 0.7  # readings under this go to a human before touching the plan


@app.post("/report")
async def report(centre_id: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if not (file.content_type or "").startswith(("audio/", "image/")):
        raise HTTPException(415, "Send an audio note or a photo")

    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=data, mime_type=file.content_type), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Report,
            temperature=0,
        ),
    )
    parsed: Report = resp.parsed
    if parsed is None:
        raise HTTPException(422, "Could not read this report. Ask for a clearer note.")

    accepted, needs_review = [], []
    for line in parsed.stock:
        (accepted if line.confidence >= REVIEW_BELOW else needs_review).append(line)

    return {
        "centre_id": centre_id,
        "apply_now": [l.model_dump() for l in accepted],
        "confirm_with_human": [l.model_dump() for l in needs_review],
        "staff_absent": parsed.staff_absent,
        "beds_free": parsed.beds_free,
        "language": parsed.language,
        "summary": parsed.transcript_summary,
    }
