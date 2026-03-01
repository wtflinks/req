from pymongo import MongoClient
from config import Config

# Connect to MongoDB Cluster
client = MongoClient(Config.MONGO_URI)

# Dynamic Database (IMPORTANT)
db = client[Config.MONGO_DB]

# Collections
users = db["users"]
groups = db["groups"]
settings = db["settings"]


# ---------------- SETTINGS FUNCTIONS ---------------- #

def get_setting(key: str):
    doc = settings.find_one({"_id": key})
    return doc.get("value") if doc else None


def set_setting(key: str, value):
    settings.update_one(
        {"_id": key},
        {"$set": {"value": value}},
        upsert=True
    )


def delete_setting(key: str):
    settings.delete_one({"_id": key})


# ---------------- USER FUNCTIONS ---------------- #

def already_db(user_id):
    return users.find_one({"user_id": str(user_id)}) is not None


def add_user(user_id):
    if not already_db(user_id):
        return users.insert_one({"user_id": str(user_id)})


def remove_user(user_id):
    if already_db(user_id):
        return users.delete_one({"user_id": str(user_id)})


def all_users():
    return users.count_documents({})


# ---------------- GROUP FUNCTIONS ---------------- #

def already_dbg(chat_id):
    return groups.find_one({"chat_id": str(chat_id)}) is not None


def add_group(chat_id):
    if not already_dbg(chat_id):
        return groups.insert_one({"chat_id": str(chat_id)})


def all_groups():
    return groups.count_documents({})