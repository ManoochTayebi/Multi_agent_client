"""Explicit mock carrier API for integration demonstrations; never a real carrier."""
from fastapi import FastAPI, HTTPException
from atlas.config import settings
from pathlib import Path
import json

app = FastAPI(title='Atlas Mock Carrier')


@app.get('/health')
def health():
    return {'status':'ok','provider':'simulation'}


@app.get('/shipments/{shipment_id}')
def shipment(shipment_id: str):
    rows = json.loads((Path(settings().data_dir)/'generated'/'shipments.json').read_text())
    row = next((x for x in rows if x['id'] == shipment_id),None)
    if not row:
        raise HTTPException(404,'Shipment not found')
    return {**row,'provider':'simulation'}
