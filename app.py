import logging
import requests
import os
import bcrypt
import pytz
from flask import Flask, request, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from database import init_db, get_user_by_username, update_last_login, get_user_by_id, add_stock, update_stock_status, get_stocks, update_stock_prices
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
_raw_origins     = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS  = [o.strip() for o in _raw_origins.split(",") if o.strip()]
CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)

STOCKS = {}
REQUEST_TIMEOUT = 10

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_stock_price(company):
    base_url = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc"
    try:
        session = get_session()
        response = session.get(url=f"{base_url}/{company}", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if 'ltp' not in data:
            raise ValueError(f"Invalid response for {company}")
        return int(data["ltp"])
    except requests.RequestException as e:
        logger.error(f"Failed to fetch price for {company}: {e}")
        raise
    except (ValueError, KeyError) as e:
        logger.error(f"Invalid data for {company}: {e}")
        raise

def load_stocks():
    global STOCKS
    STOCKS = get_stocks()


def send_telegram_msg(stock_name, curr_price, action):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("Telegram credentials not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = f"{action} {stock_name} with current price: {curr_price}"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        session = get_session()
        response = session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info(f"Telegram alert sent: {action} {stock_name}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


IST = pytz.timezone("Asia/Kolkata")


def check_stock():
    for stock in STOCKS:
        if stock["status"] == 0:
            continue
        try:
            current_price = get_stock_price(stock["name"])
            if current_price >= stock["sell_price"]:
                send_telegram_msg(stock["name"], current_price, "SELL")
            elif stock["buy_price"] <= current_price:
                send_telegram_msg(stock["name"], current_price, "BUY")
        except Exception as e:
            logger.error(f"Error processing {stock['name']}: {e}")
            continue
    print("Running scheduled task")


def create_scheduler():
    scheduler = BackgroundScheduler(timezone=IST)

    scheduler.add_job(
        func=check_stock,
        trigger=CronTrigger(
            day_of_week="mon-fri",  # Monday to Friday
            hour="9-15",  # 9 AM to 3 PM (last run at 3:55, next would be 4:00 — excluded)
            minute="15,20,25,30,35,40,45,50,55,0",  # every 5 mins
            timezone=IST
        ),
        id="market_job",
        replace_existing=True
    )

    # 4:00 PM run explicitly (last tick)
    scheduler.add_job(
        func=check_stock,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="16",
            minute="0",
            timezone=IST
        ),
        id="market_job_close",
        replace_existing=True
    )

    scheduler.start()

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status"    : "ok"
    })

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
        
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    try:
        user = get_user_by_username(username)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401

        if bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8')):
            update_last_login(user["id"])
            return jsonify({
                'message': 'Login successful',
                'user_id': user["username"],
                'firstname': user["firstname"],
                'lastname': user["lastname"],
                'id': user["id"]
            }), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        return jsonify({
            'id': user['id'],
            'email': user['email'],
            'firstname': user['firstname'],
            'lastname': user['lastname'],
            'created_at': user['created_at'],
            'last_login': user['last_login']
        }), 200
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/stock', methods=['POST'])
def add_stock_entry():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
        
    name = data.get('name')
    buy_price = data.get('buy_price')
    sell_price = data.get('sell_price')

    if not name or buy_price is None or sell_price is None:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        buy_price = float(buy_price)
        sell_price = float(sell_price)
        if buy_price < 0 or sell_price < 0:
            return jsonify({'error': 'Prices must be positive'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid price format'}), 400

    try:
        add_stock(name, sell_price, buy_price)
        load_stocks()
        return jsonify({'message': 'Stock added successfully'}), 201
    except Exception as e:
        logger.error(f"Add stock error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/stock/prices/<int:id>', methods=['PUT'])
def update_stock_entry_values(id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    buy_price = data.get('buy_price')
    sell_price = data.get('sell_price')

    if buy_price is None or sell_price is None:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        update_stock_prices(buy_price, sell_price)
        load_stocks()
        return jsonify({'message': 'Stock updated successfully'}), 200
    except Exception as e:
        logger.error(f"Update stock error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/stock/<int:id>', methods=['PUT'])
def update_stock_entry_status(id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
        
    status = data.get('status')

    if status is not None:
        if isinstance(status, str) and status.isdigit():
            status = int(status)
        if status not in [0, 1]:
            return jsonify({'error': 'Status must be 0 or 1'}), 400
    else:
        return jsonify({'error': 'Status must be 0 or 1'}), 400

    try:
        update_stock_status(id, status)
        load_stocks()
        return jsonify({'message': 'Stock updated successfully'}), 200
    except Exception as e:
        logger.error(f"Update stock error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/stocks', methods=['GET'])
def get_all_stocks():
    try:
        refresh = bool(request.args.get("refresh"))
        if refresh:
            load_stocks()
        stocks_with_prices = []
        for stock in STOCKS:
            stock_copy = stock.copy()
            try:
                stock_copy["current_price"] = get_stock_price(stock["name"])
            except Exception as e:
                logger.warning(f"Failed to fetch price for {stock['name']}: {e}")
                stock_copy["current_price"] = None
            stocks_with_prices.append(stock_copy)
        return jsonify(stocks_with_prices), 200
    except Exception as e:
        logger.error(f"Get stocks error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/stock/refresh', methods=['GET'])
def refresh_stocks():
    try:
        load_stocks()
        stocks_with_prices = []
        for stock in STOCKS:
            stock_copy = stock.copy()
            try:
                stock_copy["current_price"] = get_stock_price(stock["name"])
            except Exception as e:
                logger.warning(f"Failed to fetch price for {stock['name']}: {e}")
                stock_copy["current_price"] = None
            stocks_with_prices.append(stock_copy)
        return jsonify(stocks_with_prices), 200
    except Exception as e:
        logger.error(f"Refresh stocks error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    try:
        init_db()
        load_stocks()
        create_scheduler()
        logger.info("Application started successfully")
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
    except Exception as e:
        logger.critical(f"Failed to start application: {e}")
        raise
