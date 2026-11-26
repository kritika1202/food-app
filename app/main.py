import logging
import uuid
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated
from dotenv import load_dotenv
load_dotenv()
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.database import Base, SessionLocal, engine, get_db
from app.models import MenuItem, Order, User
from app.schemas import ItemInput, ItemResponse, OrderInput, OrderResponse, StatusInput
from app.security import admin_user, current_user
from app.seed import seed
from app.services import OrderService

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield

app = FastAPI(title="Food AI Restaurant Assistant", lifespan=lifespan)
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(admin_user)]
rate_windows = defaultdict(deque)

@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    if request.url.path.startswith("/api/"):
        now = time.monotonic()
        window = rate_windows[request.client.host if request.client else "unknown"]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 120:
            return JSONResponse(status_code=429, content={"code": "RATE_LIMITED", "message": "Too many requests. Please try again later.", "request_id": request.state.request_id}, headers={"Retry-After": "60"})
        window.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "request_id": request.state.request_id}, headers=exc.headers)

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "Invalid request", "request_id": request.state.request_id})

@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "request_id": request.state.request_id})

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/me")
def me(user: CurrentUser):
    return {"username": user.username, "role": user.role}

@app.get("/api/menu_items", response_model=list[ItemResponse])
def list_items(db: Db, category: str | None = None, vegetarian: bool | None = None, max_price: Decimal | None = None, keyword: str | None = None):
    query = select(MenuItem).where(MenuItem.active.is_(True))
    if category:
        query = query.where(MenuItem.category == category)
    if vegetarian is not None:
        query = query.where(MenuItem.vegetarian == vegetarian)
    if max_price is not None:
        query = query.where(MenuItem.price <= max_price)
    if keyword:
        query = query.where(MenuItem.title.ilike(f"%{keyword}%"))
    return db.scalars(query.order_by(MenuItem.id)).all()

@app.get("/api/menu_items/{item_id}", response_model=ItemResponse)
def get_item(item_id: int, db: Db):
    item = db.scalar(select(MenuItem).where(MenuItem.id == item_id, MenuItem.active.is_(True)))
    if not item:
        raise HTTPException(404, "Menu item not found")
    return item

@app.post("/api/menu_items", response_model=ItemResponse, status_code=201)
def create_item(body: ItemInput, db: Db, _admin: Admin):
    item = MenuItem(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.put("/api/menu_items/{item_id}", response_model=ItemResponse)
def update_item(item_id: int, body: ItemInput, db: Db, _admin: Admin):
    item = get_item(item_id, db)
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return item

@app.delete("/api/menu_items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Db, _admin: Admin):
    item = get_item(item_id, db)
    item.active = False
    db.commit()

@app.post("/api/orders", response_model=OrderResponse, status_code=201)
def create_order(body: OrderInput, db: Db, user: CurrentUser, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=120)]):
    return OrderService(db).create(user.id, body, idempotency_key)

@app.get("/api/orders", response_model=list[OrderResponse])
def list_orders(db: Db, user: CurrentUser):
    return db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()

@app.get("/api/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Db, user: CurrentUser):
    order = db.get(Order, order_id)
    if not order or (order.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Order not found")
    return order

@app.post("/api/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, db: Db, user: CurrentUser):
    return OrderService(db).cancel(user.id, order_id)

@app.patch("/api/admin/orders/{order_id}/status", response_model=OrderResponse)
def order_status(order_id: int, body: StatusInput, db: Db, _admin: Admin):
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, "Order not found")
    transitions = {"CONFIRMED": "PREPARING", "PREPARING": "READY", "READY": "DELIVERED"}
    if transitions.get(order.status) != body.status:
        raise HTTPException(409, "Invalid status transition")
    result = db.execute(update(Order).where(Order.id == order_id, Order.status == order.status).values(status=body.status))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Order status changed")
    db.commit()
    db.refresh(order)
    return order

from app.routes_chat import router as chat_router
app.include_router(chat_router)

from fastapi.staticfiles import StaticFiles
from app.database import ROOT
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")