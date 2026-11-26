import hashlib
import json
from collections import Counter
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import MenuItem, Order, OrderLine
from app.repositories import MenuRepository, OrderRepository
from app.schemas import OrderInput

class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.menu = MenuRepository(db)
        self.orders = OrderRepository(db)

    def create(self, user_id: int, request: OrderInput, key: str):
        counts = Counter()
        expected_prices = {}
        for line in request.lines:
            counts[line.item_id] += line.quantity
            if line.expected_unit_price is not None:
                if line.item_id in expected_prices and expected_prices[line.item_id] != line.expected_unit_price:
                    raise HTTPException(422, "Conflicting expected prices")
                expected_prices[line.item_id] = line.expected_unit_price
        if any(quantity > 10 for quantity in counts.values()):
            raise HTTPException(422, "Maximum quantity per item is 10")
        request_hash = hashlib.sha256(json.dumps([sorted(counts.items()), sorted((item_id, str(price)) for item_id, price in expected_prices.items())]).encode()).hexdigest()
        existing = self.db.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(409, "Idempotency key already used for a different order")
            return existing
        try:
            total = Decimal("0")
            lines = []
            for item_id, quantity in sorted(counts.items()):
                item = self.menu.active(item_id, lock=True)
                if not item:
                    raise HTTPException(404, "Menu item not found")
                if item_id in expected_prices and item.price != expected_prices[item_id]:
                    raise HTTPException(409, f"Price changed for {item.title}; please review the order again")
                conditions = [MenuItem.id == item_id, MenuItem.active.is_(True), MenuItem.capacity >= quantity]
                if item_id in expected_prices:
                    conditions.append(MenuItem.price == expected_prices[item_id])
                changed = self.db.execute(update(MenuItem).where(*conditions).values(capacity=MenuItem.capacity - quantity))
                if changed.rowcount != 1:
                    self.db.rollback()
                    replay = self.db.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))
                    if replay and replay.request_hash == request_hash:
                        return replay
                    raise HTTPException(409, f"Price or availability changed for {item.title}")
                total += item.price * quantity
                lines.append(OrderLine(item_id=item_id, quantity=quantity, unit_price=item.price))
            order = Order(user_id=user_id, total=total, idempotency_key=key, request_hash=request_hash, lines=lines)
            self.db.add(order)
            self.db.commit()
            return order
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))
            if existing and existing.request_hash == request_hash:
                return existing
            raise HTTPException(409, "Order conflicts with an existing request")
        except Exception:
            self.db.rollback()
            raise

    def cancel(self, user_id: int, order_id: int):
        order = self.orders.owned(order_id, user_id, lock=True)
        if not order:
            raise HTTPException(404, "Order not found")
        changed = self.db.execute(update(Order).where(Order.id == order_id, Order.status == "CONFIRMED").values(status="CANCELLED"))
        if changed.rowcount != 1:
            self.db.rollback()
            raise HTTPException(409, "Order cannot be cancelled")
        for line in order.lines:
            self.db.execute(update(MenuItem).where(MenuItem.id == line.item_id).values(capacity=MenuItem.capacity + line.quantity))
        self.db.commit()
        self.db.refresh(order)
        return order