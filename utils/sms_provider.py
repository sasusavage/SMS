"""
SMS Provider Wrapper - Hubtel/Arkesel Ghanaian Gateway
"""
import requests
import os
from flask import current_app

def send_sms(phone, message):
    """
    Sends an SMS via a Ghanaian SMS Gateway (Mock implementation for now).
    In production, this calls Arkesel or Hubtel API.
    """
    sender_id = os.environ.get('SMS_SENDER_ID', 'SmartSch')
    api_key = os.environ.get('SMS_API_KEY')
    
    print(f"--- SMS SENT TO {phone} [{sender_id}] ---")
    print(f"Message: {message}")
    print("---------------------------------------")
    
    # Example logic for Arkesel:
    # url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key={api_key}&to={phone}&from={sender_id}&sms={message}"
    # response = requests.get(url)
    # return response.status_code == 200
    
    return True
