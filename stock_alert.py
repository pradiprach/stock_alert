from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP

import requests
import os


def send_alert(stock_name, curr_price, action):
    my_email = os.environ.get("SMTP_EMAIL")
    password = os.environ.get("SMTP_PASSWORD")
    to_email = os.environ.get("TO_EMAIL")

    msg = f"{action} {stock_name} with current price: {curr_price}"
    message = MIMEMultipart()
    message['From'] = my_email
    message['To'] = to_email
    message['Subject'] = msg
    message.attach(MIMEText(msg, 'plain'))

    with SMTP("smtp-relay.brevo.com", port=587) as connection:
        connection.starttls()
        connection.login(user=my_email, password=password)
        connection.sendmail(from_addr=my_email, to_addrs=to_email, msg=message.as_string())

def send_telegram_msg(stock_name, curr_price, action):
    # Your credentials
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")  # Use the negative ID for groups

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message = f"{action} {stock_name} with current price: {curr_price}"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Message sent to family!")
        else:
            print(f"Failed to send: {response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")


def check_stock_price():
    companies = {
        "RELIANCE": {
            "buy": 1220,
            "sell": 1600
        },
        "IRCTC": {
            "buy": 580,
            "sell": 900
        },
        "LICI": {
            "buy": 700,
            "sell": 1020
        },
        "OLAELEC": {
            "buy": 25,
            "sell": 43
        },
        "INDIGO": {
            "buy": 4200,
            "sell": 5500
        }
    }
    base_url = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc"
    for company in companies:
        response =  requests.get(url=f"{base_url}/{company}")
        share_price = int(response.json()["ltp"])
        print(f"Company: {company}, Current Price: {share_price}")
        if companies[company]["buy"] > share_price:
            send_telegram_msg(company, share_price, "BUY")
        elif companies[company]["sell"] < share_price:
            send_telegram_msg(company, share_price, "SELL")


if __name__ == "__main__":
    check_stock_price()
