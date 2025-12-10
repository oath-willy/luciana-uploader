from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.db import SessionLocal
from sqlalchemy import text

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    #rows = db.execute(text("SELECT * FROM products_test")).fetchall()
    rows = db.execute(text("SELECT * FROM dbo.v_products_all")).fetchall()

    # convert SQL rows to JSON
    data = []
    for row in rows:
        data.append(dict(row._mapping))
    return data
