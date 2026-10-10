"""
core/services/categorization_service.py
Hybrid Categorization Engine:
  1. PayeeMapping lookup for (user, payee_key) → returns mapped category with confidence 1.0.
  2. Fallback to scikit-learn CalibratedClassifierCV(RandomForestClassifier) model
     trained on transaction features:
       - amount
       - amount_bucket
       - hour_of_day
       - day_of_week
       - payee_frequency so far this month for this user
       - token features from remark / UPI ID / payee name / raw text
"""

from __future__ import annotations

import os
import re
import string
import logging
from datetime import date, time, datetime
from decimal import Decimal
from typing import Tuple, Dict, Any, List, Optional

import numpy as np
import pandas as pd
import joblib
from django.conf import settings
from django.contrib.auth.models import User
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV

from ..models import ExpenseCategory, PayeeMapping, Transaction

logger = logging.getLogger(__name__)

# Canonical model path
MODEL_DIR = os.path.join(settings.BASE_DIR, "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "categorizer_model.joblib")

# In-memory cached pipeline
_CACHED_MODEL: Optional[Pipeline] = None

# List of all categories
CATEGORIES: List[str] = [c.value for c in ExpenseCategory]


# ---------------------------------------------------------------------------
# Normalization Helper
# ---------------------------------------------------------------------------

def normalize_payee(name: str | None = None, upi_id: str | None = None) -> str:
    """
    Normalizes payee identity into a consistent lookup key.
    Rules:
      - Lowercase
      - Strip punctuation and extra spaces
      - Prefer the UPI ID as the key when present
    """
    raw = ""
    is_upi = False

    if upi_id and str(upi_id).strip():
        raw = str(upi_id).strip()
        is_upi = True
    elif name and str(name).strip():
        raw = str(name).strip()

    if not raw:
        return ""

    lowered = raw.lower()

    if is_upi:
        # Keep standard UPI address characters (alphanumeric, @, ., -), strip whitespace and noise
        cleaned = re.sub(r"[^\w@.-]", "", lowered)
        cleaned = cleaned.strip(".-")
        return cleaned
    else:
        # For payee names, replace punctuation with space, collapse whitespace
        cleaned = re.sub(r"[^\w\s]", " ", lowered)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned


# ---------------------------------------------------------------------------
# Feature Extraction Helpers
# ---------------------------------------------------------------------------

def get_amount_bucket(amount: float) -> str:
    """Discretizes transaction amount into meaningful student spending tiers."""
    amt = float(amount)
    if amt < 100:
        return "micro"       # < 100 (tea, xerox, snacks)
    elif amt < 300:
        return "low"         # 100 - 300 (fast food, auto, quick groceries)
    elif amt < 800:
        return "medium"      # 300 - 800 (dining, cab, groceries, movie)
    elif amt < 2000:
        return "high"        # 800 - 2000 (shopping, party split, subscriptions)
    elif amt < 6000:
        return "very_high"   # 2000 - 6000 (academics, textbooks, clothing)
    else:
        return "large"       # > 6000 (hostel fee, rent, semester fee)


def extract_features(
    transaction: Transaction | Dict[str, Any],
    payee_frequency: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Extracts tabular + text features from a Transaction instance or dict.
    Returns:
      {
        'amount': float,
        'amount_bucket': str,
        'hour_of_day': int,
        'day_of_week': int,
        'payee_frequency': int,
        'text': str,
      }
    """
    if isinstance(transaction, dict):
        amount = float(transaction.get("amount", 0.0) or 0.0)
        t_time = transaction.get("time")
        t_date = transaction.get("date")
        payee_name = str(transaction.get("payee_name", "") or "")
        upi_id = str(transaction.get("upi_id", "") or "")
        remark = str(transaction.get("remark", "") or "")
        raw_text = str(transaction.get("raw_text", "") or "")
        user = transaction.get("user")
    else:
        amount = float(transaction.amount or 0.0)
        t_time = transaction.time
        t_date = transaction.date
        payee_name = transaction.payee_name or ""
        upi_id = transaction.upi_id or ""
        remark = transaction.remark or ""
        raw_text = transaction.raw_text or ""
        user = getattr(transaction, "user", None)

    # Hour of day (0-23)
    if isinstance(t_time, time):
        hour_of_day = t_time.hour
    elif isinstance(t_time, str) and ":" in t_time:
        try:
            hour_of_day = int(t_time.split(":")[0])
        except ValueError:
            hour_of_day = 14
    else:
        hour_of_day = 14  # sensible default (afternoon)

    # Day of week (0=Mon, 6=Sun)
    if isinstance(t_date, date):
        day_of_week = t_date.weekday()
    elif isinstance(t_date, str):
        try:
            day_of_week = datetime.strptime(t_date[:10], "%Y-%m-%d").date().weekday()
        except ValueError:
            day_of_week = 0
    else:
        day_of_week = 0

    # Payee frequency so far this month for this user
    if payee_frequency is not None:
        freq = int(payee_frequency)
    elif user and isinstance(t_date, date):
        try:
            freq = Transaction.objects.filter(
                user=user,
                date__year=t_date.year,
                date__month=t_date.month,
                payee_name=payee_name,
            ).count()
            # If current transaction is already in DB, freq is at least 1
            freq = max(1, freq)
        except Exception:
            freq = 1
    else:
        freq = 1

    # Token features from remark / UPI ID / payee / raw_text
    text_tokens = f"{payee_name} {upi_id} {remark} {raw_text}".strip()

    return {
        "amount": amount,
        "amount_bucket": get_amount_bucket(amount),
        "hour_of_day": int(hour_of_day),
        "day_of_week": int(day_of_week),
        "payee_frequency": int(freq),
        "text": text_tokens,
    }


# ---------------------------------------------------------------------------
# Synthetic Dataset Generation (270 rows across 9 categories)
# ---------------------------------------------------------------------------

def generate_synthetic_dataset() -> pd.DataFrame:
    """
    Generates a realistic synthetic labeled dataset reflecting student UPI patterns.
    Contains 270 rows (30 per category) covering Food, Travel, Groceries/Shopping,
    Subscriptions, Rent/Hostel, Academics, Friend/Split, Entertainment, and Other.
    """
    rows = []

    # 1. FOOD (30 items: Zomato, Swiggy, Canteens, Chai, Street Food, Cafes)
    food_samples = [
        ("Zomato", "zomato@hdfcbank", "Order from Behrouz Biryani", 320.0, 20, 4, 3),
        ("Swiggy", "swiggy@icici", "Swiggy order #892182", 215.0, 13, 2, 5),
        ("Campus Canteen", "canteen@upi", "Lunch thali special", 60.0, 13, 1, 12),
        ("Tapri Chai", "tapri@paytm", "Chai and bun maska", 30.0, 9, 3, 15),
        ("Dominos Pizza", "dominos@icici", "Regular Margherita pizza", 249.0, 21, 5, 2),
        ("McDonalds", "mcdonalds@hdfcbank", "McVeggie meal burger fries", 199.0, 14, 6, 1),
        ("Burger King", "burgerking@axisbank", "Whopper combo meal", 239.0, 19, 0, 2),
        ("Chai Point", "chaipoint@axl", "Ginger chai flask ginger biscuit", 120.0, 10, 2, 4),
        ("Mess Advance", "mess.hostel@sbi", "Monthly mess extra food coupons", 500.0, 12, 0, 1),
        ("Sharma Dhaba", "sharmadhaba@paytm", "Paneer butter masala 3 roti", 180.0, 21, 3, 6),
        ("Haldiram", "haldirams@kotak", "Chole bhature lassi", 160.0, 15, 6, 1),
        ("Subway", "subway@hdfcbank", "Sub of the day cookie drink", 220.0, 13, 4, 2),
        ("Pizza Hut", "pizzahut@icici", "Personal pan pizza garlic bread", 280.0, 20, 5, 1),
        ("Wow Momo", "wowmomo@axl", "Steam darjeeling momo plate", 110.0, 17, 1, 3),
        ("Chai Sutta Bar", "csb@paytm", "Kulhad chai and maggi", 55.0, 18, 4, 8),
        ("Nescafe Kiosk", "nescafe@upi", "Cold coffee with crushed oreo", 45.0, 16, 2, 10),
        ("Tibbs Frankie", "frankie@paytm", "Paneer schezwan frankie", 90.0, 17, 3, 4),
        ("Kathi Roll Corner", "kathiroll@okaxis", "Double egg double chicken roll", 130.0, 22, 5, 3),
        ("Anna Idli Dosa", "annadosa@upi", "Masala dosa filter coffee breakfast", 75.0, 8, 1, 7),
        ("Maggi Point", "maggipoint@paytm", "Cheese butter peri peri maggi", 60.0, 23, 4, 9),
        ("Late Night Paratha", "paratha@upi", "Aloo paratha curd pickle butter", 80.0, 23, 6, 5),
        ("Starbucks", "starbucks@hdfcbank", "Iced caffe latte tall", 345.0, 16, 0, 1),
        ("Cafe Coffee Day", "ccd@icici", "Cappuccino chocolate pastry", 195.0, 17, 5, 2),
        ("Rolls Mania", "rollsmania@paytm", "Cheesy paneer roll", 115.0, 20, 3, 2),
        ("Dosa Plaza", "dosaplaza@okaxis", "Mysore masala dosa", 95.0, 9, 0, 3),
        ("Chaat Gali", "chaat@upi", "Pani puri dahi puri sev puri", 70.0, 18, 2, 4),
        ("Biryani Blues", "biryaniblues@icici", "Chicken dum biryani mini", 250.0, 14, 5, 2),
        ("Faasos", "faasos@hdfcbank", "Jumbo falafel roll combo", 210.0, 21, 1, 3),
        ("Baskin Robbins", "baskinrobbins@axisbank", "Mississippi mud scoop", 140.0, 22, 6, 1),
        ("Natural Ice Cream", "naturals@paytm", "Tender coconut scoop waffle cone", 90.0, 21, 4, 2),
    ]
    for name, upi, remark, amt, hr, dow, freq in food_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.FOOD,
        })

    # 2. TRAVEL (30 items: Uber, Ola, Rapido, Metro, Rail, Buses, Fuel)
    travel_samples = [
        ("Uber India", "uber.india@hdfcbank", "Uber Go ride to railway station", 280.0, 8, 0, 4),
        ("Ola Cabs", "olacabs@icici", "Mini cab ride to college gate", 145.0, 9, 1, 3),
        ("Rapido", "rapido@upi", "Rapido bike taxi ride to metro station", 45.0, 8, 2, 10),
        ("Namma Metro", "bmrc.metro@axisbank", "Metro smart card recharge QR", 200.0, 9, 0, 2),
        ("Delhi Metro DMRC", "dmrc.metro@paytm", "DMRC top up recharge ticket", 150.0, 17, 3, 3),
        ("IRCTC Train", "irctc@sbi", "IRCTC Tatkal train ticket to home", 840.0, 10, 4, 1),
        ("RedBus", "redbus@hdfcbank", "Intercity Volvo AC sleeper bus booking", 650.0, 18, 5, 1),
        ("Chalo Card", "chalocard@yesbank", "City bus monthly travel pass", 350.0, 11, 0, 1),
        ("Indian Oil Petrol", "iocppetrol@paytm", "Bike fuel petrol tank fill", 300.0, 15, 2, 3),
        ("HPCL Petrol Pump", "hpcl@icici", "Scooter petrol 3 litres fuel", 320.0, 16, 5, 2),
        ("Auto Rickshaw", "autorickshaw@upi", "Meter auto ride college to hostel", 50.0, 18, 3, 8),
        ("AbhiBus", "abhibus@axisbank", "Overnight bus return journey ticket", 580.0, 21, 6, 1),
        ("MakeMyTrip Bus", "makemytrip@icici", "Bus ticket reservation return trip", 720.0, 12, 4, 1),
        ("Uber Auto", "uber.india@hdfcbank", "Uber Auto ride to exam hall", 75.0, 8, 1, 5),
        ("Ola Auto", "olacabs@icici", "Ola Auto ride city center mall", 95.0, 14, 6, 2),
        ("Rapido Auto", "rapido@upi", "Rapido auto ride home", 65.0, 19, 2, 4),
        ("Bharat Petroleum BPCL", "bpcl@sbi", "Petrol filling station payment", 250.0, 12, 3, 3),
        ("Mumbai Local Rail", "uts.railways@sbi", "Local train quarterly pass season ticket", 360.0, 10, 0, 1),
        ("Zoomcar Self Drive", "zoomcar@hdfcbank", "Weekend car rental deposit share", 1200.0, 7, 5, 1),
        ("BluSmart Mobility", "blusmart@icici", "Electric cab ride airport drop", 450.0, 6, 4, 1),
        ("Toll Plaza FASTag", "fastag@paytm", "Highway toll plaza automatic debit", 85.0, 11, 6, 1),
        ("Bicycle Rental", "yulu.bikes@axl", "Yulu electric bike ride commute", 35.0, 17, 1, 6),
        ("Bounce Daily", "bounce@upi", "Scooter rental 2 hour ride", 90.0, 15, 3, 2),
        ("Goibibo Bus", "goibibo@hdfcbank", "Bus ticket to hometown Diwali vacation", 890.0, 20, 4, 1),
        ("Auto Driver", "driver.upi@okaxis", "Shared auto stand fare", 25.0, 9, 2, 12),
        ("Railway Canteen PRS", "irctcticket@paytm", "Railway platform ticket and unreserved", 30.0, 7, 0, 2),
        ("Uber Go", "uber.india@hdfcbank", "Short trip to hospital clinic", 120.0, 11, 3, 2),
        ("Shell Petrol", "shellpetrol@paytm", "Premium petrol scooter refill", 400.0, 19, 5, 2),
        ("Chartered Bus", "charteredbus@upi", "Campus shuttle transport fee", 500.0, 10, 0, 1),
        ("Airport Metro Express", "dmrc.express@paytm", "Express line token to terminal", 60.0, 8, 5, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in travel_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.TRAVEL,
        })

    # 3. GROCERIES/SHOPPING (30 items: Blinkit, Zepto, Instamart, Amazon, Flipkart, Supermarkets)
    grocery_samples = [
        ("Blinkit", "blinkit@icici", "Milk bread eggs butter snacks 10 min", 185.0, 8, 0, 6),
        ("Zepto", "zepto@hdfcbank", "Maggi biscuits cold drink curd fruits", 220.0, 19, 2, 5),
        ("Instamart Swiggy", "swiggyinstamart@icici", "Detergent dishwash chips juice", 310.0, 20, 4, 4),
        ("Amazon India", "amazonpay@apl", "Order for USB-C cable laptop sleeve", 649.0, 14, 1, 2),
        ("Flipkart", "flipkart@axisbank", "Power bank 10000mAh purchase", 899.0, 15, 3, 1),
        ("Myntra", "myntra@icici", "Cotton casual t-shirts and socks", 1150.0, 21, 5, 1),
        ("DMart Ready", "dmart@hdfcbank", "Monthly hostel provision shampoo biscuits", 980.0, 16, 6, 1),
        ("Reliance Fresh", "reliancefresh@sbi", "Vegetables fruits rice cooking oil", 450.0, 11, 2, 2),
        ("BigBasket BB Daily", "bigbasket@icici", "Daily milk and curd subscription", 350.0, 7, 0, 4),
        ("Local Kirana Store", "kirana@upi", "Soap toothpaste washing powder coil", 160.0, 18, 3, 3),
        ("More Supermarket", "morestores@kotak", "Snacks dry fruits peanut butter honey", 520.0, 17, 5, 1),
        ("Nykaa Man", "nykaa@hdfcbank", "Facewash deodorant hair wax", 480.0, 16, 0, 1),
        ("Ajio", "ajio@axisbank", "Sneakers shoes sports running", 1499.0, 20, 4, 1),
        ("Decathlon", "decathlon@icici", "Gym water bottle resistance band wristband", 399.0, 17, 6, 1),
        ("Blinkit Quick", "blinkit@icici", "Late night ice cream chips coke", 140.0, 23, 5, 4),
        ("Zepto Groceries", "zepto@hdfcbank", "Oats almond milk banana peanut butter", 360.0, 9, 1, 3),
        ("Zudio", "zudio@tata", "Casual hoodie and sweatpants", 799.0, 18, 6, 1),
        ("Lenskart", "lenskart@hdfcbank", "Computer glasses blue cut lenses", 1200.0, 13, 2, 1),
        ("Amazon Fresh", "amazonfresh@apl", "Apples bananas bread peanut butter", 420.0, 10, 4, 2),
        ("Tata 1mg Mart", "tata1mg@icici", "Protein bar multivitamin dry fruit", 650.0, 15, 3, 1),
        ("Nature Basket", "naturesbasket@axisbank", "Imported noodles gourmet coffee dark chocolate", 450.0, 18, 5, 1),
        ("Smart Bazaar", "smartbazaar@sbi", "Bed sheet pillow cover laundry bag", 599.0, 14, 0, 1),
        ("Snackible", "snackible@paytm", "Healthy ragi chips roasted makhana", 220.0, 16, 2, 2),
        ("JioMart", "jiomart@axisbank", "Atta pulses spices monthly groceries", 850.0, 12, 1, 1),
        ("Croma Electronics", "croma@icici", "Earphones replacement wired 3.5mm", 399.0, 15, 4, 1),
        ("Urbanic", "urbanic@hdfcbank", "Casual denim jacket summer", 1290.0, 21, 5, 1),
        ("Blinkit Essentials", "blinkit@icici", "Mosquito repellent coil room spray", 195.0, 20, 3, 2),
        ("Patanjali Store", "patanjali@upi", "Herbal shampoo aloe vera gel toothpaste", 175.0, 11, 6, 1),
        ("Supermart Provision", "supermart@okaxis", "Eggs brown bread curd dairy items", 110.0, 8, 4, 5),
        ("Flipkart Grocery", "flipkartgrocery@axisbank", "Instant noodles combo pack cereal", 380.0, 13, 1, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in grocery_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.GROCERIES_SHOPPING,
        })

    # 4. SUBSCRIPTIONS (30 items: Spotify, Netflix, YouTube, Prime, Cloud, AI tools)
    sub_samples = [
        ("Spotify India", "spotify@upi", "Spotify Premium Student monthly subscription", 59.0, 1, 0, 1),
        ("Netflix India", "netflix.in@hdfcbank", "Netflix Mobile monthly plan subscription", 149.0, 2, 1, 1),
        ("YouTube Premium", "googleplay@sbi", "YouTube Premium student membership recurring", 79.0, 0, 2, 1),
        ("Amazon Prime", "amazonpay@apl", "Prime annual youth student subscription", 749.0, 10, 4, 1),
        ("Hotstar Disney", "hotstar@icici", "Disney+ Hotstar super annual subscription", 499.0, 14, 5, 1),
        ("ChatGPT OpenAI", "openai@stripe", "ChatGPT Plus monthly subscription AI", 1650.0, 12, 3, 1),
        ("GitHub Copilot", "github@paypal", "GitHub Copilot individual recurring charge", 850.0, 15, 0, 1),
        ("Apple iCloud", "apple.services@paytm", "iCloud+ 50GB monthly cloud storage", 75.0, 3, 1, 1),
        ("Google One", "googleplay@sbi", "Google One 100GB monthly plan Drive", 130.0, 4, 2, 1),
        ("LinkedIn Premium", "linkedin@hdfcbank", "LinkedIn Learning career student discount", 1199.0, 11, 4, 1),
        ("Notion AI", "notion@stripe", "Notion Plus education workspace annual", 450.0, 16, 6, 1),
        ("Claude Anthropic", "anthropic@stripe", "Claude Pro monthly subscription LLM", 1680.0, 13, 2, 1),
        ("Sony LIV", "sonyliv@icici", "Sony LIV mobile annual plan sports", 399.0, 19, 5, 1),
        ("JioCinema Premium", "jiocinema@axisbank", "JioCinema Premium annual plan", 29.0, 17, 3, 1),
        ("Medium Member", "medium@stripe", "Medium monthly reading membership", 410.0, 8, 0, 1),
        ("Duolingo Super", "duolingo@googleplay", "Duolingo Super language learning yearly", 799.0, 9, 6, 1),
        ("Chess.com Diamond", "chesscom@paypal", "Chess.com Gold monthly membership", 299.0, 22, 1, 1),
        ("LeetCode Premium", "leetcode@stripe", "LeetCode annual student discount coding", 1250.0, 10, 5, 1),
        ("Audible India", "audible@amazon", "Audible audiobook monthly recurring credits", 199.0, 11, 2, 1),
        ("Coursera Plus", "coursera@stripe", "Coursera monthly specialization subscription", 999.0, 14, 4, 1),
        ("Grammarly Premium", "grammarly@paypal", "Grammarly student writing tool quarterly", 890.0, 15, 1, 1),
        ("Apple Music", "apple.services@paytm", "Apple Music student plan lossless", 59.0, 2, 3, 1),
        ("Zee5 Premium", "zee5@hdfcbank", "Zee5 12 month entertainment plan", 499.0, 20, 6, 1),
        ("Canva Pro", "canva@stripe", "Canva Pro design suite annual billing", 499.0, 12, 0, 1),
        ("Overleaf Pro", "overleaf@stripe", "Overleaf LaTeX student research plan", 350.0, 16, 2, 1),
        ("Midjourney AI", "midjourney@stripe", "Midjourney Basic plan generative art", 820.0, 18, 4, 1),
        ("ProtonMail VPN", "proton@paypal", "Proton Unlimited secure email and VPN", 450.0, 10, 1, 1),
        ("GeeksforGeeks Premium", "gfg@axisbank", "GFG annual practice portal membership", 799.0, 13, 5, 1),
        ("Blinkist", "blinkist@googleplay", "Blinkist book summaries student plan", 399.0, 9, 3, 1),
        ("Perplexity Pro", "perplexity@stripe", "Perplexity AI search monthly pro", 1650.0, 14, 0, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in sub_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.SUBSCRIPTIONS,
        })

    # 5. RENT/HOSTEL (30 items: Landlord, PG, Hostel fee, Electricity, Maintenance)
    rent_samples = [
        ("Landlord Sharma", "sharma.rent@okaxis", "Monthly flat rent October 2BHK share", 8500.0, 10, 0, 1),
        ("Hostel Warden", "hostel.warden@sbi", "Hostel accommodation fees semester 1", 12000.0, 11, 1, 1),
        ("Sharma PG Services", "sharmapg@paytm", "PG monthly stay double sharing room", 7500.0, 9, 2, 1),
        ("Flat 302 Maintenance", "greenwood.society@hdfcbank", "Apartment maintenance society charges", 1200.0, 12, 0, 1),
        ("Security Deposit", "landlord.deposit@okicici", "Refundable house security deposit share", 15000.0, 14, 5, 1),
        ("Hostel Electricity", "bescom.electricity@axisbank", "Hostel AC electricity meter sub-reading", 1450.0, 16, 3, 1),
        ("Roommate Rent Split", "roommate.split@okaxis", "Share of apartment monthly rent contribution", 6500.0, 18, 1, 1),
        ("Stanza Living PG", "stanzaliving@hdfcbank", "Co-living PG accommodation monthly installment", 11500.0, 10, 0, 1),
        ("Zolo Stays PG", "zolostays@icici", "Zolo monthly rental private room", 9500.0, 11, 2, 1),
        ("Campus Hostel Office", "collegerector@sbi", "Room allotment hostel caution money deposit", 8000.0, 13, 4, 1),
        ("House Owner Gupta", "gupta.owner@okaxis", "Rent for flat 404 November", 9000.0, 10, 1, 1),
        ("PG Food and Stay", "sai.pg@paytm", "Monthly paying guest rent with food", 6800.0, 9, 0, 1),
        ("Water Bill Society", "societywater@axisbank", "Apartment tanker water charges share", 450.0, 15, 4, 1),
        ("Hostel Mess Deposit", "hostelmess@sbi", "Hostel mess caution deposit advance", 5000.0, 12, 0, 1),
        ("Flatmate Rent Share", "flatmate99@okaxis", "Half share of October house rent", 7000.0, 20, 1, 1),
        ("PG Room Rent", "anandpg@paytm", "Triple sharing PG bed rent", 5500.0, 10, 2, 1),
        ("Apartment Gas Pipeline", "adanigas@icici", "Piped cooking gas bill flat share", 380.0, 14, 3, 1),
        ("Hostel Laundry Service", "hostellaundry@upi", "Semester washing machine maintenance fee", 800.0, 11, 5, 1),
        ("Landlord Verma", "verma.property@okaxis", "Quarterly advance room rent", 21000.0, 11, 0, 1),
        ("Boys Hostel Warden", "boyshostel@sbi", "Semester 3 hostel room fee", 14000.0, 10, 1, 1),
        ("CoLive Rooms", "colive@hdfcbank", "Monthly colive rent single occupancy", 10500.0, 12, 2, 1),
        ("Girls Hostel Fee", "girlshostel@sbi", "Hostel room and mess charge semester", 13500.0, 11, 3, 1),
        ("Landlady Patel", "patel.house@okicici", "Studio apartment monthly rent", 9200.0, 9, 0, 1),
        ("PG AC Bill", "pgowner@paytm", "Monthly power consumption AC unit", 1800.0, 17, 4, 1),
        ("Flat Wifi Bill Split", "airtelbroadband@icici", "Fiber broadband internet bill flatmate share", 400.0, 15, 2, 1),
        ("Hostel Gym Fee", "campusgym@upi", "Hostel fitness center term subscription", 600.0, 16, 5, 1),
        ("Broker Brokerage", "realestate@paytm", "One time flat rental brokerage brokerage share", 4500.0, 13, 6, 1),
        ("Society Clubhouse", "greensociety@axisbank", "Apartment sports facility fee", 300.0, 14, 1, 1),
        ("Hostel Key Deposit", "hosteloffice@sbi", "Hostel locker and room key deposit", 1000.0, 10, 0, 1),
        ("Flat Painter Repair", "homeservice@paytm", "Plumber carpentry maintenance repair split", 650.0, 16, 3, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in rent_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.RENT_HOSTEL,
        })

    # 6. ACADEMICS (30 items: Xerox, Books, Printouts, Exam fee, Stationery, Courses)
    academic_samples = [
        ("Xerox Centre", "xerox.hub@upi", "Semester notes assignment photocopies", 35.0, 11, 1, 8),
        ("Printout Hub", "printout@paytm", "Project final report color printout binding", 120.0, 15, 3, 5),
        ("College Bookstore", "collegebooks@sbi", "Engineering mathematics and physics textbook", 850.0, 14, 0, 2),
        ("Stationery Mart", "stationery@okaxis", "Classmate notebooks pens graph paper", 180.0, 16, 2, 4),
        ("Coursera Course", "coursera@paypal", "Machine learning course certification fee", 2499.0, 18, 5, 1),
        ("Udemy Online", "udemy@hdfcbank", "Web development bootcamp tutorial course", 499.0, 21, 6, 1),
        ("College Exam Cell", "examcell@sbi", "Semester examination registration form fee", 1800.0, 10, 0, 1),
        ("Library Fine", "library@college.edu", "Late book return fine payment", 40.0, 12, 4, 3),
        ("Scientific Calculator", "casio.store@icici", "Casio fx-991EX scientific calculator", 1250.0, 13, 1, 1),
        ("Lab Manual Store", "labmanuals@upi", "Digital electronics lab manual sheets", 90.0, 10, 2, 3),
        ("IEEE Student Branch", "ieee.student@sbi", "Annual IEEE student chapter membership", 1500.0, 15, 4, 1),
        ("Speed Post College", "indiapost@sbi", "Transcript courier speed post envelope", 75.0, 12, 1, 1),
        ("Drawing Instruments", "artstationery@paytm", "Mini drafter engineering drawing sheet", 420.0, 11, 2, 1),
        ("NPTEL Exam Fee", "nptel@sbi", "NPTEL online course exam proctoring fee", 1000.0, 14, 3, 1),
        ("Technical Symposium", "collegetechfest@upi", "Hackathon team registration fee", 300.0, 17, 5, 2),
        ("Campus ID Card", "admin.office@sbi", "Duplicate college smart ID card fee", 200.0, 11, 0, 1),
        ("Research Paper Fee", "springer@paypal", "Conference workshop registration student", 3000.0, 16, 4, 1),
        ("GRE Test Prep", "ets.gre@hdfcbank", "Official GRE practice mock test materials", 2100.0, 19, 6, 1),
        ("Photocopy Shop", "campuscpu@upi", "Syllabus question paper copies", 25.0, 9, 1, 10),
        ("Book Depo", "prabhatbooks@paytm", "Reference handbook data structures algorithms", 550.0, 13, 3, 1),
        ("Whiteboard Markers", "stationeryworld@upi", "Duster markers sticky notes for group study", 130.0, 15, 2, 2),
        ("Arduino Robotics Kit", "robu.in@hdfcbank", "Microcontroller breadboard sensors semester project", 1650.0, 14, 5, 1),
        ("Tuition Math Tutor", "tutor.upi@okaxis", "Monthly calculus coaching class tuition", 2000.0, 17, 0, 1),
        ("Sticker & Chart Paper", "artsupplies@paytm", "Poster presentation chart sheet pins", 85.0, 16, 3, 2),
        ("Resume Printing", "quickprint@upi", "Glossy paper resume print copies interview", 50.0, 10, 4, 3),
        ("Degree Verification", "univoffice@sbi", "Attestation mark sheet transcript processing", 500.0, 12, 1, 1),
        ("HackerRank Pack", "hackerrank@stripe", "Coding assessment certification prep", 750.0, 18, 5, 1),
        ("Project Hardware Parts", "electronicscomp@upi", "Jumper wires resistors capacitor kit", 260.0, 15, 2, 2),
        ("Seminar Registration", "acmchapter@upi", "ACM student conference pass", 450.0, 11, 4, 1),
        ("Dictionary & Grammar", "oxfordpress@icici", "English communication vocabulary handbook", 320.0, 13, 0, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in academic_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.ACADEMICS,
        })

    # 7. FRIEND/SPLIT (30 items: Splitwise, Roomies, Trip settlement, Treats)
    split_samples = [
        ("Splitwise Settle", "splitwise@hdfcbank", "Settle up dinner bill from yesterday", 340.0, 21, 4, 4),
        ("Rahul Verma", "rahul99@okaxis", "Share of weekend dinner and snacks", 220.0, 22, 5, 6),
        ("Priya Sharma", "priya.s@icici", "Split for birthday gift contribution", 350.0, 18, 6, 3),
        ("Amit Kumar", "amit.k@paytm", "Goa trip fuel split settlement", 850.0, 14, 0, 2),
        ("Rohan Flatmate", "rohan.flat@okaxis", "Groceries and drinking water can split", 180.0, 20, 2, 7),
        ("Settle Up Bhai", "bhai.settle@upi", "Bhai treat share pizza night", 260.0, 23, 5, 5),
        ("Trip Contribution", "tripcaptain@icici", "Nandi hills bike trip breakfast split", 190.0, 11, 6, 2),
        ("Ankit Singh", "ankit.s@okaxis", "Money borrowed for tea and snacks return", 70.0, 16, 1, 8),
        ("Neha Gupta", "neha.gupta@paytm", "Fare share for shared cab to mall", 110.0, 19, 3, 4),
        ("Hostel Wing Treat", "wingcaptain@upi", "Wing party snacks cold drinks fund", 300.0, 22, 6, 2),
        ("Vikas Roomie", "vikas98@icici", "WiFi bill half payment splitwise", 299.0, 15, 0, 3),
        ("Pooja Patel", "pooja.p@okaxis", "Cafe coffee bill half split", 145.0, 17, 2, 3),
        ("Karan Verma", "karan.v@paytm", "Movie popcorn and tickets split share", 420.0, 21, 5, 2),
        ("Deepak Settle", "deepak@okaxis", "Cricket turf booking ground split", 150.0, 18, 6, 3),
        ("Ayush Sharma", "ayush@icici", "Dominos bill split 4 people", 210.0, 22, 4, 4),
        ("Roomie Ration Split", "roomie.groceries@upi", "Cooking oil vegetables splitwise", 250.0, 19, 1, 5),
        ("Saurabh Mishra", "saurabh.m@paytm", "Treat money paid by friend settlement", 180.0, 20, 3, 4),
        ("Gaurav Flat", "gaurav.flat@okaxis", "Apartment maid salary monthly share", 750.0, 10, 0, 2),
        ("Manish Kumar", "manish.k@icici", "Badminton court rental share", 90.0, 7, 5, 3),
        ("Shreya Sen", "shreya.sen@paytm", "Group project material cost share", 160.0, 16, 2, 2),
        ("Tushar Bhai", "tushar@okaxis", "Night mess food split settlement", 125.0, 23, 3, 6),
        ("Varun Joshi", "varun.j@icici", "Weekend highway dhaba bill split", 310.0, 21, 6, 2),
        ("Harshvardhan", "harsh@paytm", "Bowling alley game ticket share", 240.0, 17, 4, 1),
        ("Friend Loan Repay", "friendloan@upi", "Returned the 500 borrowed last week", 500.0, 12, 1, 2),
        ("Alok Pandey", "alok.p@okaxis", "Potluck dinner ingredients share", 175.0, 20, 5, 2),
        ("Divya Roy", "divya.roy@icici", "Shopping split Myntra combo order", 480.0, 18, 0, 1),
        ("Canteen Split Bhai", "canteenbhai@upi", "Lunch bill split canteen", 85.0, 13, 2, 7),
        ("Mohit Yadav", "mohit.y@paytm", "Gokarting race ticket share split", 350.0, 16, 6, 1),
        ("Siddharth Settle", "sid.split@okaxis", "Electricity bill equal share roommate", 400.0, 14, 1, 2),
        ("Late Night Chai Split", "chaisplit@upi", "Tea and smoke tapri split with bros", 40.0, 23, 4, 9),
    ]
    for name, upi, remark, amt, hr, dow, freq in split_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.FRIEND_SPLIT,
        })

    # 8. ENTERTAINMENT (30 items: Movies, Games, Outings, Concerts, Events)
    ent_samples = [
        ("BookMyShow", "bookmyshow@icici", "Movie tickets PVR IMAX 3D Kalki 2898 AD", 480.0, 19, 5, 2),
        ("PVR Cinemas", "pvrcinemas@hdfcbank", "Cinema tickets and tub popcorn combo", 620.0, 20, 6, 2),
        ("INOX Leisure", "inox@axisbank", "Evening movie show recliner seat", 380.0, 18, 4, 1),
        ("Steam Games", "steamgames@paytm", "Steam Summer Sale Counter Strike game skin", 450.0, 22, 2, 2),
        ("PlayStation Store", "sony.psn@hdfcbank", "PS Plus membership game addon", 799.0, 21, 3, 1),
        ("Bowling Alley SMAAASH", "smaaash@icici", "2 games bowling and arcade laser tag", 550.0, 17, 6, 1),
        ("Gaming Cafe Arena", "gamingcafe@upi", "4 hours PC gaming high-end RTX 4080", 240.0, 16, 5, 3),
        ("Standup Comedy Show", "comedyclub@paytm", "Zakir Khan live standup show ticket", 750.0, 19, 6, 1),
        ("Concert Tickets Insider", "insider@hdfcbank", "College cultural fest EDM night pass", 600.0, 20, 5, 1),
        ("Escape Room", "escaperoom@icici", "Mystery room puzzle game ticket", 400.0, 15, 6, 1),
        ("Cinepolis", "cinepolis@axisbank", "VIP seats popcorn beverage combo", 520.0, 21, 4, 1),
        ("Board Game Cafe", "boardgames@upi", "Entry fee and cold drinks afternoon play", 180.0, 16, 0, 2),
        ("Amusement Park Wonderla", "wonderla@hdfcbank", "Student discount water rides day ticket", 1150.0, 10, 5, 1),
        ("Valorant Points Riot", "riotgames@paytm", "In-game battle pass skin purchase", 799.0, 23, 1, 2),
        ("Pubg BGMI UC", "krafton@googleplay", "Royale pass UC pack game credits", 380.0, 22, 4, 2),
        ("Museum & Planetarium", "sciencecenter@sbi", "3D show ticket Nehru Planetarium entry", 80.0, 11, 6, 1),
        ("Go Karting Speed", "speedwaykart@upi", "6 laps go karting track racing", 450.0, 17, 5, 1),
        ("Music Festival Sunburn", "sunburn@insider", "Early bird day 1 pass festival", 1499.0, 18, 6, 1),
        ("IPL Match Tickets", "bcci.ipl@icici", "Chinnaswamy Stadium match stand ticket", 1250.0, 14, 0, 1),
        ("Pool & Snooker Club", "snookerarena@upi", "2 hours snooker table rental", 160.0, 18, 2, 4),
        ("Carnival Cinemas", "carnival@paytm", "Matinee cinema ticket", 150.0, 13, 1, 1),
        ("Laser Tag Zone", "lasertag@okaxis", "Team laser battle 2 rounds", 300.0, 17, 5, 1),
        ("Trampoline Park", "skyjumper@hdfcbank", "60 mins bounce trampoline pass", 450.0, 16, 6, 1),
        ("Paintball Arena", "paintball@upi", "50 balls combat tactical paintball", 350.0, 15, 5, 1),
        ("Karaoke Night Lounge", "karaokebar@icici", "Song session cover charge beverage", 280.0, 21, 3, 1),
        ("Circus / Magic Show", "magicshow@paytm", "Evening illusionist stage show pass", 200.0, 19, 0, 1),
        ("Comic Con Ticket", "comiccon@insider", "Super fan weekend entry badge pass", 899.0, 12, 5, 1),
        ("Wave Cinema", "wavecinemas@sbi", "Movie tickets with nacho combo", 320.0, 20, 2, 1),
        ("Anime Convention", "animefest@paytm", "Cosplay convention day pass entry", 400.0, 13, 6, 1),
        ("Night Club Entry", "clubentry@upi", "Weekend club cover charge entry pass", 800.0, 23, 5, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in ent_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.ENTERTAINMENT,
        })

    # 9. OTHER (30 items: Pharmacy, Medical, ATM, Mobile recharges, Courier, Misc)
    other_samples = [
        ("Apollo Pharmacy", "apollopharmacy@hdfcbank", "Paracetamol bandaid cough syrup tablets", 145.0, 12, 1, 2),
        ("MedPlus Mart", "medplus@axisbank", "Vitamins eye drops antiseptic ointment", 210.0, 19, 3, 2),
        ("Jio Prepaid Recharge", "jio.recharge@paytm", "Jio 5G true unlimited 84 days plan", 666.0, 11, 0, 1),
        ("Airtel Mobile Recharge", "airtel@axisbank", "Monthly smartphone 1.5GB daily recharge", 299.0, 15, 2, 1),
        ("ATM Cash Withdrawal", "sbi.atm@sbi", "Cash withdrawal for auto emergency", 1000.0, 16, 4, 1),
        ("Dr Clinic Consultation", "drclinic@okaxis", "General physician consultation fever checkup", 300.0, 18, 1, 1),
        ("Speed Post Courier", "indiapost@sbi", "Document speed post envelope dispatch", 65.0, 13, 2, 1),
        ("Dry Cleaners Laundry", "dryclean@paytm", "Blazer and jacket dry clean wash", 280.0, 17, 6, 1),
        ("Shoe Repair Cobbler", "shoerepair@upi", "Sneaker sole pasting repair polish", 50.0, 14, 5, 1),
        ("Eye Hospital Clinic", "eyecare@hdfcbank", "Vision testing refraction power check", 250.0, 10, 0, 1),
        ("Dentist Dental Clinic", "dentist@icici", "Teeth scaling polishing appointment", 600.0, 16, 3, 1),
        ("Phone Screen Guard", "mobileaccessories@upi", "Tempered glass screen protector installation", 120.0, 17, 2, 1),
        ("Passport Seva Kendra", "passport.govt@sbi", "Passport renewal tatkal application charge", 1500.0, 10, 1, 1),
        ("Diagnostic Lab Blood Test", "lalpathlabs@hdfcbank", "Complete blood count test CBC", 450.0, 8, 4, 1),
        ("Key Maker Locksmith", "keymaker@upi", "Duplicate room key making", 80.0, 15, 1, 1),
        ("Vi Vodafone Idea", "myvi@paytm", "Prepaid mobile pack recharge 28 days", 249.0, 14, 0, 1),
        ("Government Stamp Paper", "stampduty@sbi", "Non judicial stamp paper for agreement", 100.0, 11, 3, 1),
        ("Tailor Alteration", "tailorshop@upi", "Trouser hem fitting and shirt stitching", 90.0, 18, 5, 2),
        ("Watch Battery Repair", "timexrepair@paytm", "Wrist watch battery cell replacement", 70.0, 16, 6, 1),
        ("Charity Donation", "pmcares@sbi", "Student relief donation support", 100.0, 12, 6, 1),
        ("Umbrella Raincoat Store", "monsoonstore@upi", "Foldable windproof rain umbrella", 250.0, 15, 2, 1),
        ("Bag Zip Repair", "bagrepair@paytm", "Backpack zipper puller replacement", 40.0, 17, 4, 1),
        ("Hardware Nut Bolt", "hardwaremart@upi", "Screwdriver bicycle pedal nut repair", 60.0, 14, 0, 1),
        ("Pet Food Supplies", "petshop@axisbank", "Cat food whiskas pouch", 180.0, 19, 3, 1),
        ("Hair Salon Barber", "mensalon@upi", "Haircut and beard trim", 150.0, 11, 6, 3),
        ("Police Verification Fee", "policeverification@sbi", "Character certificate challan payment", 200.0, 10, 2, 1),
        ("Gym Shaker Bottle", "plasticmart@paytm", "BPA free plastic water container", 110.0, 16, 5, 1),
        ("Medical Pharmacy 24x7", "lifelinechemist@upi", "ORS packets bandaid volini spray", 130.0, 22, 1, 2),
        ("Print Visa Photograph", "photostudio@paytm", "Passport size photographs urgent copies", 80.0, 12, 4, 1),
        ("Lost Wallet Recovery", "rickshawunion@upi", "Gratuity reward return lost bag", 200.0, 18, 5, 1),
    ]
    for name, upi, remark, amt, hr, dow, freq in other_samples:
        rows.append({
            "amount": amt,
            "amount_bucket": get_amount_bucket(amt),
            "hour_of_day": hr,
            "day_of_week": dow,
            "payee_frequency": freq,
            "text": f"{name} {upi} {remark}".strip(),
            "category": ExpenseCategory.OTHER,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# ML Model Pipeline & Training
# ---------------------------------------------------------------------------

def build_model_pipeline() -> Pipeline:
    """
    Constructs the feature transformation and calibrated classifier pipeline.
    Uses:
      - TfidfVectorizer for token features from text (remark/UPI ID/payee)
      - OneHotEncoder for amount_bucket
      - StandardScaler for numeric features (amount, hour, day, frequency)
      - CalibratedClassifierCV wrapping RandomForestClassifier
    """
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "text",
                TfidfVectorizer(
                    max_features=250,
                    ngram_range=(1, 2),
                    token_pattern=r"(?u)\b\w+\b",
                ),
                "text",
            ),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore"),
                ["amount_bucket"],
            ),
            (
                "num",
                StandardScaler(),
                ["amount", "hour_of_day", "day_of_week", "payee_frequency"],
            ),
        ]
    )

    base_rf = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight="balanced",
    )

    calibrated_classifier = CalibratedClassifierCV(
        estimator=base_rf,
        cv=3,
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", calibrated_classifier),
        ]
    )
    return pipeline


def train_model(
    df: Optional[pd.DataFrame] = None,
    save_path: Optional[str] = None,
) -> Tuple[Pipeline, Dict[str, Any]]:
    """
    Trains the hybrid classifier on the given DataFrame (or synthetic dataset).
    Saves artifact to `save_path` (defaults to MODEL_PATH).
    Returns (fitted_pipeline, metrics_dict).
    """
    global _CACHED_MODEL

    if df is None or df.empty:
        df = generate_synthetic_dataset()

    feature_cols = [
        "amount",
        "amount_bucket",
        "hour_of_day",
        "day_of_week",
        "payee_frequency",
        "text",
    ]
    X = df[feature_cols]
    y = df["category"]

    pipeline = build_model_pipeline()
    pipeline.fit(X, y)

    target_path = save_path or MODEL_PATH
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    joblib.dump(pipeline, target_path)

    # Update in-memory cache
    _CACHED_MODEL = pipeline

    metrics = {
        "samples_trained": len(df),
        "categories_count": len(y.unique()),
        "categories": list(y.unique()),
        "saved_to": target_path,
    }
    logger.info("Trained categorizer model with %d samples → %s", len(df), target_path)
    return pipeline, metrics


def get_or_load_model() -> Pipeline:
    """
    Returns the loaded Pipeline. If not in memory, loads from disk.
    If not on disk, automatically trains on the synthetic dataset and saves it.
    """
    global _CACHED_MODEL
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL

    if os.path.exists(MODEL_PATH):
        try:
            _CACHED_MODEL = joblib.load(MODEL_PATH)
            return _CACHED_MODEL
        except Exception as e:
            logger.warning("Failed loading cached model from %s: %s. Retraining.", MODEL_PATH, e)

    # Train and persist fresh model
    pipeline, _ = train_model(save_path=MODEL_PATH)
    return pipeline


def route_status_from_confidence(confidence: float) -> str:
    """
    Confidence-based status routing:
      - confidence >= 0.80 -> 'auto'
      - 0.50 <= confidence < 0.80 -> 'verify'
      - confidence < 0.50 -> 'pending' (needs student's help)
    """
    if confidence >= 0.80:
        return Transaction.ParseStatus.AUTO
    elif confidence >= 0.50:
        return Transaction.ParseStatus.VERIFY
    else:
        return Transaction.ParseStatus.PENDING


# ---------------------------------------------------------------------------
# Categorization Service (Per-transaction & Batch)
# ---------------------------------------------------------------------------

def categorize_transaction(
    transaction: Transaction,
    save: bool = True,
) -> Tuple[str, float, str]:
    """
    Core hybrid categorizer:
      1. Look up PayeeMapping for this user + payee_key. If found → confidence 1.0.
      2. Otherwise, extract features and run calibrated ML classifier → category + confidence.
      3. Routes status based on confidence:
         confidence >= 0.80 -> 'auto'
         0.50-0.80          -> 'verify'
         < 0.50             -> 'pending'

    Returns:
      (category: str, confidence: float, source: 'payee_mapping' | 'ml_model')
    """
    user = getattr(transaction, "user", None)
    payee_key = normalize_payee(transaction.payee_name, transaction.upi_id)

    # 1 — Check user's saved PayeeMapping
    if user and payee_key:
        mapping = PayeeMapping.objects.filter(
            user=user, payee_key=payee_key
        ).first()
        if mapping:
            cat = mapping.category
            conf = 1.0
            routed_status = route_status_from_confidence(conf)
            if save:
                transaction.category = cat
                transaction.confidence = conf
                transaction.status = routed_status
                transaction.save(update_fields=["category", "confidence", "status"])
            return cat, conf, "payee_mapping"

    # 2 — Run ML Classifier
    features = extract_features(transaction)
    df_feat = pd.DataFrame([features])

    model = get_or_load_model()
    pred_category = str(model.predict(df_feat)[0])

    probs = model.predict_proba(df_feat)[0]
    classes = list(model.classes_)
    if pred_category in classes:
        idx = classes.index(pred_category)
        confidence = float(probs[idx])
    else:
        confidence = float(np.max(probs))

    # Keep confidence bounded [0.0, 1.0] and rounded
    confidence = round(max(0.01, min(1.0, confidence)), 4)
    routed_status = route_status_from_confidence(confidence)

    if save:
        transaction.category = pred_category
        transaction.confidence = confidence
        transaction.status = routed_status
        transaction.save(update_fields=["category", "confidence", "status"])

    return pred_category, confidence, "ml_model"


def categorize_transactions(
    transactions: List[Transaction],
    save: bool = True,
) -> List[Tuple[str, float, str]]:
    """Runs hybrid categorization over a list or QuerySet of transactions."""
    return [categorize_transaction(tx, save=save) for tx in transactions]
