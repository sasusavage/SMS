"""
SMS Notification Service
Handles outgoing alerts for payments, attendance, and general announcements.
Placeholder for Arkesel or Vynfy API.
"""
import requests
import os

class SMSGateway:
    
    @staticmethod
    def send_sms(phone, message, sender_id="SMARTSCHOOL"):
        """Sends an SMS via Arkesel/Placeholder API."""
        api_key = os.environ.get('ARKESEL_API_KEY')
        if not api_key:
            print(f"SMS MOCK [To: {phone}]: {message}")
            return True, "Mock Sent"
            
        # Actual API Example (Arkesel)
        # url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key={api_key}&to={phone}&from={sender_id}&sms={message}"
        # try:
        #     response = requests.get(url)
        #     return response.status_code == 200, response.text
        # except Exception as e:
        #     return False, str(e)
        
        return True, "Success"

    @staticmethod
    def trigger_payment_receipt(student_name, phone, amount_ghs, invoice_id):
        """Sends an automated payment confirmation receipt."""
        message = (
            f"Hello, Payment of GHS {amount_ghs} for {student_name} "
            f"(Invoice #{invoice_id}) has been received successfully. "
            f"Thank you for choosing NaCCA Academy."
        )
        return SMSGateway.send_sms(phone, message)

    @staticmethod
    def trigger_absence_alert(student_name, phone, date_str):
        """Notifies parent when child is marked absent."""
        message = (
            f"IMPORTANT: {student_name} was marked ABSENT today, {date_str}. "
            f"Please contact the school office if you believe this is an error."
        )
        return SMSGateway.send_sms(phone, message)
