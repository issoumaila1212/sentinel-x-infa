from database import init_db
from mqtt_client import start

if __name__ == "__main__":
    init_db()
    start()