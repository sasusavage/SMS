from flask import Blueprint, request, jsonify, current_app
from models import db, SchoolSetting
from services.ai_agent import SasuAIAgent
import os
import requests

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

# WhatsApp API Base
WHATSAPP_VERSION = "v17.0"
WHATSAPP_URL = f"https://graph.facebook.com/{WHATSAPP_VERSION}"

@ai_bp.route('/whatsapp/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    """Multi-tenant WhatsApp Hub for Sasu AI 2.0."""
    
    # 1. Webhook Verification (for Meta)
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == os.environ.get('WHATSAPP_VERIFY_TOKEN'):
            return challenge, 200
        return "Verification failed", 403

    # 2. Logic: Process Incoming Message
    data = request.json
    if not data or 'entry' not in data:
        return jsonify({"status": "no_data"}), 200
        
    entry = data['entry'][0]['changes'][0]['value']
    if 'messages' not in entry:
        return jsonify({"status": "no_message"}), 200

    message = entry['messages'][0]
    phone_number = message['from'] # Sender (Parent/Staff)
    phone_number_id = entry['metadata']['phone_number_id'] # Target (School's WhatsApp Account)
    
    # 3. Identify Tenant (Multi-Tenancy)
    setting = SchoolSetting.query.filter_by(whatsapp_business_id=phone_number_id).first()
    if not setting or not setting.ai_bot_enabled:
        return jsonify({"status": "school_not_configured"}), 200

    agent = SasuAIAgent(setting.school_id)
    
    # 4. Detect Message Type (Text vs Voice)
    if 'text' in message:
        user_message = message['text']['body']
        ai_reply = agent.run(phone_number, user_message)
    elif 'voice' in message:
        voice_id = message['voice']['id']
        # Download and Transcribe (requires WHATSAPP_ACCESS_TOKEN)
        audio_url_res = requests.get(f"{WHATSAPP_URL}/{voice_id}", headers={"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"})
        audio_url = audio_url_res.json().get('url')
        
        # Download binary
        audio_data = requests.get(audio_url, headers={"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"}).content
        audio_path = f"temp_voice_{voice_id}.ogg"
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        
        # Transcribe
        transcription = agent.process_voice_note(audio_path)
        os.remove(audio_path) # Cleanup
        
        # Run AI with transcription
        ai_reply = agent.run(phone_number, f"[Voice Note Transcription]: {transcription}", is_voice=True)
    else:
        return jsonify({"status": "unsupported_media"}), 200
    
    # 5. Send WhatsApp Reply back to user
    send_whatsapp_message(phone_number_id, phone_number, ai_reply)
    
    return jsonify({"status": "success", "reply": ai_reply}), 200

def send_whatsapp_message(from_id, to_phone, message):
    """Utility wrapper for Meta Graph API (WhatsApp)."""
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN") # Global token or could be school-level
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message}
    }
    try:
        r = requests.post(f"{WHATSAPP_URL}/{from_id}/messages", headers=headers, json=payload)
        r.raise_for_status()
    except Exception as e:
        print(f"WhatsApp send error: {e}")

@ai_bp.route('/feedback', methods=['POST'])
def ai_feedback():
    """Submit rating for the latest AI interaction."""
    from models import AISession, AICorrection
    data = request.json
    phone = data.get('phone')
    school_id = data.get('school_id')
    feedback = data.get('feedback') # 'good', 'bad'
    reason = data.get('reason') # Required if bad
    
    session = AISession.query.filter_by(school_id=school_id, phone_number=phone).order_by(AISession.last_interaction.desc()).first()
    if not session:
        return jsonify({"status": "error", "message": "Session not found"}), 404
        
    session.user_feedback = feedback
    
    if feedback == 'bad' and reason:
        # Log correction for prompt injection
        # Identify the last assistant message from history
        last_ai_msg = session.history[-1]['content'] if session.history else ""
        last_user_msg = session.history[-2]['content'] if len(session.history) > 1 else ""
        
        correction = AICorrection(
            school_id=school_id,
            original_prompt=last_user_msg,
            wrong_response=last_ai_msg,
            correction_reason=reason
        )
        db.session.add(correction)
    
    db.session.commit()
    return jsonify({"status": "success", "message": "Feedback recorded."})

# Register in app.py
