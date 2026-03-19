from app.db.session import SessionLocal, Base, engine
from app.db.models import User
from app.core.security import hash_password
import sys

Base.metadata.create_all(bind=engine)

def create_user(username: str, password: str):
    db = SessionLocal()
    try:
        hashed = hash_password(password)
        user = User(username=username, hashed_password=hashed)
        db.add(user)
        db.commit()
        print(f"User '{username}' created successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_user.py <username> <password>")
        sys.exit(1)
    username, password = sys.argv[1], sys.argv[2]
    create_user(username, password)