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


def check_stock_price():
    companies = {
        "TCS": {
            "buy": 3200,
            "sell": 4400
        },
        "RELIANCE": {
            "buy": 1220,
            "sell": 1550
        },
        "IRCTC": {
            "buy": 670,
            "sell": 900
        },
        "LICI": {
            "buy": 700,
            "sell": 900
        },
        "PAYTM": {
            "buy": 500,
            "sell": 900
        }
    }
    base_url = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc"
    for company in companies:
        response =  requests.get(url=f"{base_url}/{company}")
        share_price = int(response.json()["ltp"])
        print(f"Company: {company}, Current Price: {share_price}")
        if companies[company]["buy"] > share_price:
            send_alert(company, share_price, "BUY")
        elif companies[company]["sell"] < share_price:
            send_alert(company, share_price, "SELL")


if __name__ == "__main__":
    check_stock_price()
