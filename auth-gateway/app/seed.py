import json
import os

from app.config import Settings
from app.policy import DEALER, SELLER
from app.users import UserStore

SEED_ROLES = {"alice": SELLER, "bob": SELLER, "dealer": DEALER}


def main():
    settings = Settings.from_env()
    seed_file = os.environ.get("SEED_USERS_FILE", "/run/secrets/seed_users")
    with open(seed_file) as f:
        passwords = json.load(f)

    missing = set(SEED_ROLES) - set(passwords)
    if missing:
        raise SystemExit(f"missing seed passwords for: {', '.join(sorted(missing))}")

    store = UserStore(settings.db_path)
    store.init_schema()
    store.remove_all_except(SEED_ROLES)
    for username, role in SEED_ROLES.items():
        store.upsert(username, passwords[username], role)
        print(f"seeded {username} ({role})")


if __name__ == "__main__":
    main()
