import os
import json
from decimal import Decimal
from datetime import datetime
try:
    from groq import Groq
except ImportError:
    Groq = None
from models import db, School, FeeInvoice, TerminalReportView, SubjectPerformanceView, Attendance, Student, AISession, AIBotConfig, SupportTicket, AICreditUsage, AuditLog, SchoolInsight, AICorrection, Product, ProductCategory, Order, OrderItem, PaymentStatus, User
from sqlalchemy import func

class SasuAIAgent:
    """The Intelligent Multi-tenant AI Hub for Ghanaian Schools."""
    
    def __init__(self, school_id):
        self.school_id = school_id
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY")) if Groq else None
        self.school = School.query.get(school_id)
        self.config = AIBotConfig.query.filter_by(school_id=school_id).first()
        
    def log_ai_action(self, action, entity_type, entity_id, detail):
        """Standardized Audit Logging for AI-triggered events."""
        log = AuditLog(
            school_id=self.school_id,
            user_id=None, # System/AI Actor
            action=f"AI_{action}",
            entity_type=entity_type,
            entity_id=entity_id,
            new_values={"actor": "Sasu AI", "detail": detail}
        )
        db.session.add(log)
        db.session.commit()

    def get_system_prompt(self, phone=None):
        # 1. Fetch latest School Insights
        insights = SchoolInsight.query.filter_by(school_id=self.school_id, is_active=True).order_by(SchoolInsight.created_at.desc()).limit(10).all()
        insight_summary = "\n".join([f"- {i.type.upper()}: {i.insight_text}" for i in insights]) if insights else "No specific outliers detected today."
        
        # 2. Fetch Learning Corrections
        corrections = AICorrection.query.filter_by(school_id=self.school_id, is_applied=True).order_by(AICorrection.created_at.desc()).limit(5).all()
        correction_history = "\n".join([f"- PREVIOUS MISTAKE CORRECTION: {c.correction_reason}" for c in corrections]) if corrections else "No corrections recorded yet."

        base_prompt = f"""
        You are {self.school.name} Adaptive Learning Agent, 'Sasu Jnr'. 
        You follow NaCCA (Ghana) standards strictly when explaining academic performance.
        Professional yet approachable. You can use friendly Ghanaian Pidgin or Twi if the user initiates it or uses voice notes in those languages.
        If the transcription you receive is in Twi or Pidgin, respond in kind to match the parent's vibe and build trust.
        
        CRITICAL CONTEXT (School-wide Analytics):
        {insight_summary}
        
        ADAPTIVE LEARNING (Feedback Loops):
        {correction_history}
        
        School Info:
        - Name: {self.school.name}
        - Motto: {self.school.motto}
        - Knowledge Base: {self.config.knowledge_base if self.config else 'Standard school rules apply.'}
        
        Guardrails:
        - ALWAYS verify identity via phone number for sensitive data.
        - NEVER hallucinate grades. If data is missing, suggest contacting the school office.
        - Be PROACTIVE: If you see an attendance drop in the School Insights, mention it to staff users.
        """
        return {"role": "system", "content": base_prompt}

    # =========================================================================
    # AGENTIC TOOLS (Read/Write)
    # =========================================================================
    
    def get_student_info(self, phone):
        """Returns student name, class, and today's attendance status."""
        from models import Parent, Student, Attendance
        from datetime import date

        parent = Parent.query.filter_by(primary_contact_phone=phone, school_id=self.school_id).first()
        if not parent: return "No linked parent account found."
        
        kids = Student.query.filter_by(parent_id=parent.id, school_id=self.school_id).all()
        res = []
        for k in kids:
            att = Attendance.query.filter_by(student_id=k.id, date=date.today()).first()
            status = att.status.value if att else "Not Yet Recorded"
            res.append(f"- {k.full_name} | Attendance Today: {status}")
        
        self.log_ai_action("FETCH_INFO", "student", parent.id, f"Checked info for {phone}")
        return "\n".join(res)

    def check_fees(self, phone):
        """Returns outstanding balance and a secure Paystack link."""
        from models import Parent, Student, FeeInvoice
        parent = Parent.query.filter_by(primary_contact_phone=phone, school_id=self.school_id).first()
        if not parent: return "No parent account found."
        
        kids = Student.query.filter_by(parent_id=parent.id, school_id=self.school_id).all()
        lines = []
        for k in kids:
            inv = FeeInvoice.query.filter_by(student_id=k.id, school_id=self.school_id).order_by(FeeInvoice.created_at.desc()).first()
            if inv:
                pay_link = f"https://paystack.com/pay/{inv.uuid}" # Placeholder
                lines.append(f"{k.full_name}: GHS {inv.balance:,.2f} | Pay: {pay_link}")
        
        return "\n".join(lines) if lines else "Clear! No outstanding fees found."

    def explain_nacca_grade(self, student_name):
        """Explains NaCCA strands/sub-strands based on live grades."""
        student = Student.query.filter(
            (func.lower(Student.first_name).contains(student_name.lower()) | 
             func.lower(Student.last_name).contains(student_name.lower())),
            Student.school_id == self.school_id
        ).first()
        
        if not student: return "I couldn't find that student."
        
        grades = SubjectPerformanceView.query.filter_by(student_id=student.id).all()
        if not grades: return "Grades not yet uploaded for this term."
        
        response = f"Academic Breakdown for {student.full_name}:\n"
        for g in grades:
            # Join with Subject to get string name if needed, assuming id is fine for now
            response += f"- Subject ID {g.subject_id}: {g.nacca_grade} ({g.total_score}%). Target the specific Sub-strands for improvement!\n"
        
        return response

    def create_support_ticket(self, phone, issue):
        """Logs a support ticket for the school administration."""
        ticket = SupportTicket(
            school_id=self.school_id,
            phone_number=phone,
            description=issue,
            subject="WhatsApp AI Inquiry"
        )
        db.session.add(ticket)
        db.session.commit()
        
        self.log_ai_action("CREATE_TICKET", "support_ticket", ticket.id, f"Ticket from {phone}")
        return f"Done! I've logged ticket #{ticket.id} for the Office. They will call you soon."

    def list_marketplace_items(self):
        """Returns categories and active items for WhatsApp shopping."""
        items = Product.query.filter_by(school_id=self.school_id, is_active=True).limit(5).all()
        if not items: return "The school store hasn't listed any items yet."
        res = ["*School Store Inventory:*"]
        for p in items:
            res.append(f"- ID {p.id}: {p.name} | GHS {p.base_price:,.2f}")
        res.append("\nReply with 'Sasu order [ID]' to buy.")
        return "\n".join(res)

    def create_market_order(self, phone, product_id, qty=1):
        """Builds a marketplace order via WhatsApp."""
        # Find user by phone
        user = User.query.filter_by(school_id=self.school_id).first() # Simplified
        product = Product.query.get(product_id)
        
        if not product or not product.is_active: return "Sorry, that item is unavailable."
        if product.stock_quantity < qty: return f"Only {product.stock_quantity} left in stock."
        
        order = Order(
            school_id=self.school_id,
            user_id=1, # Admin/Default User for now
            total_amount=product.base_price * qty,
            status=PaymentStatus.PENDING
        )
        db.session.add(order)
        db.session.flush()
        
        oi = OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price=product.base_price, subtotal=product.base_price * qty)
        db.session.add(oi)
        db.session.commit()

        self.log_ai_action("CREATE_ORDER", "order", order.id, f"WhatsApp order for product {product_id}")
        pay_url = f"https://paystack.com/pay/ORDER_{order.id}_ELITE"
        return f"Order #{order.id} placed for {product.name} x{qty}. Total: GHS {order.total_amount:,.2f}\nPay here: {pay_url}"

    def process_voice_note(self, audio_file_path):
        """Transcribes WhatsApp voice notes using OpenAI Whisper."""
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    prompt="The audio is from a parent of a school in Ghana. It might be in English, Pidgin, or Twi."
                )
            return transcription.text
        except Exception as e:
            return f"Error transcribing voice: {str(e)}"

    def run(self, phone, user_message, is_voice=False):
        """Engine with tool-calling and credit tracking."""
        session = AISession.query.filter_by(school_id=self.school_id, phone_number=phone).first()
        if not session:
            session = AISession(school_id=self.school_id, phone_number=phone, history=[])
            db.session.add(session)
        
        messages = [self.get_system_prompt()]
        messages.extend(session.history[-6:])
        messages.append({"role": "user", "content": user_message})
        
        tools = [
            {"type": "function", "function": {"name": "get_student_info", "description": "Get student status/attendance", "parameters": {"type": "object", "properties": {"phone": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "check_fees", "description": "Check outstanding balance", "parameters": {"type": "object", "properties": {"phone": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "explain_nacca_grade", "description": "Explain grades in detail", "parameters": {"type": "object", "properties": {"student_name": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "create_support_ticket", "description": "Log official school ticket", "parameters": {"type": "object", "properties": {"issue": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "list_marketplace_items", "description": "See school items (Uniforms, books)", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "create_market_order", "description": "Buy a school item", "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}, "qty": {"type": "integer"}}}}}
        ]
        
        response = self.client.chat.completions.create(
            model="llama3-8b-8192", messages=messages, tools=tools, tool_choice="auto"
        )
        
        ai_msg = response.choices[0].message
        
        if ai_msg.tool_calls:
            for tc in ai_msg.tool_calls:
                fn = tc.function.name
                args = json.loads(tc.function.arguments)
                
                if fn == "get_student_info": res = self.get_student_info(phone)
                elif fn == "check_fees": res = self.check_fees(phone)
                elif fn == "explain_nacca_grade": res = self.explain_nacca_grade(args.get("student_name"))
                elif fn == "create_support_ticket": res = self.create_support_ticket(phone, args.get("issue"))
                elif fn == "list_marketplace_items": res = self.list_marketplace_items()
                elif fn == "create_market_order": res = self.create_market_order(phone, args.get("product_id"), args.get("qty", 1))
                else: res = "Error: Tool unavailable."
                
                messages.append(ai_msg)
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": fn, "content": res})
            
            final = self.client.chat.completions.create(model="llama3-8b-8192", messages=messages)
            reply = final.choices[0].message.content
        else:
            reply = ai_msg.content
            
        # Log Credit Usage
        usage = AICreditUsage(school_id=self.school_id, tokens_used=150, interaction_type="whatsapp")
        db.session.add(usage)
        
        session.history.append({"role": "user", "content": user_message})
        session.history.append({"role": "assistant", "content": reply})
        db.session.commit()
        return reply
