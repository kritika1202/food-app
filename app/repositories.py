from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import MenuItem, Order

class MenuRepository:
    def __init__(self, db: Session):
        self.db = db

    def active(self, item_id: int, lock: bool = False):
        query = select(MenuItem).where(MenuItem.id == item_id, MenuItem.active.is_(True))
        return self.db.scalar(query.with_for_update() if lock else query)

class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def owned(self, order_id: int, user_id: int, lock: bool = False):
        query = select(Order).where(Order.id == order_id, Order.user_id == user_id)
        return self.db.scalar(query.with_for_update() if lock else query)