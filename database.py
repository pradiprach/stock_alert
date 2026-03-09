from datetime import datetime
import logging
import pytz
from supabase import create_client, Client
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def init_db():
    """
    Supabase does not support schema creation via SDK.
    This function is kept only for compatibility.
    """
    pass

def get_user_by_username(username: str):
    """Fetch user by username."""
    try:
        response = (
            supabase
            .table("users")
            .select("*")
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error fetching user by username: {e}")
        raise


def get_user_by_id(user_id: int):
    """Fetch user by ID."""
    try:
        response = (
            supabase
            .table("users")
            .select("*")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error fetching user by ID: {e}")
        raise


def update_last_login(user_id: int):
    """Update last login timestamp for user."""
    try:
        ist = pytz.timezone('Asia/Kolkata')
        supabase.table("users").update({
            "last_login": datetime.now(ist).isoformat()
        }).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"Error updating last login: {e}")
        raise


def add_stock(name: str, sell_price: float, buy_price: float):
    """Add a new stock to the database."""
    try:
        response = supabase.table("stocks").insert({
            "name": name,
            "sell_price": sell_price,
            "buy_price": buy_price,
            "status": 0
        }).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error adding stock: {e}")
        raise


def update_stock_status(id: int, status: int):
    """Update stock status."""
    try:
        supabase.table("stocks").update({
            "status": status
        }).eq("id", id).execute()
    except Exception as e:
        logger.error(f"Error updating stock status: {e}")
        raise


def get_stocks():
    """Get all stocks from the database."""
    try:
        response = supabase.table("stocks").select("*").order("name", desc=False).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching stocks: {e}")
        raise
