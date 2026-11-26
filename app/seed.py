from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import MenuItem, User
from app.security import hasher

ITEMS = [
    ("Masala Dosa", "Breakfast", True, "90.00", 20, "Crisp rice crepe with spiced potato"),
    ("Paneer Biryani", "Main course", True, "180.00", 10, "Fragrant rice with paneer and spices"),
    ("Idli Sambar", "Breakfast", True, "80.00", 18, "Steamed rice cakes with lentil stew"),
    ("Chole Bhature", "Main course", True, "150.00", 12, "Chickpea curry with fluffy bread"),
    ("Dal Tadka", "Main course", True, "140.00", 16, "Yellow lentils with aromatic tempering"),
    ("Chicken Biryani", "Main course", False, "220.00", 10, "Spiced rice with tender chicken"),
    ("Grilled Chicken", "Main course", False, "240.00", 8, "Herb-marinated grilled chicken"),
    ("Veg Pulao", "Main course", True, "130.00", 15, "Basmati rice with seasonal vegetables"),
    ("Mango Lassi", "Drinks", True, "70.00", 20, "A chilled mango and yogurt drink"),
    ("Gulab Jamun", "Dessert", True, "60.00", 20, "Soft milk dumplings in syrup"),
]

def seed(db: Session):
    fresh = not db.scalar(select(User.id).limit(1))
    if fresh:
        for username, role in [("admin", "admin"), ("maya", "user"), ("arjun", "user")]:
            db.add(User(username=username, password_hash=hasher.hash("demo1234"), role=role))
    if not db.scalar(select(MenuItem.id).limit(1)):
        for title, category, vegetarian, price, capacity, description in ITEMS:
            db.add(MenuItem(title=title, category=category, vegetarian=vegetarian, price=price, capacity=capacity, description=description))
    db.commit()
    if fresh:
        from app.schemas import OrderInput
        from app.services import OrderService
        service = OrderService(db)
        for username, item_title, order_status in [("maya", "Masala Dosa", "CONFIRMED"), ("maya", "Paneer Biryani", "PREPARING"), ("arjun", "Idli Sambar", "DELIVERED")]:
            user = db.scalar(select(User).where(User.username == username))
            item = db.scalar(select(MenuItem).where(MenuItem.title == item_title))
            order = service.create(user.id, OrderInput.model_validate({"lines": [{"item_id": item.id, "quantity": 1}]}), f"seed-{username}-{item.id}")
            order.status = order_status
            db.commit()