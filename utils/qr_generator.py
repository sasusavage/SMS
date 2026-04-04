import qrcode
import io
import json
import base64

def generate_student_qr(student_uuid, school_id):
    """
    Generates a QR code for a student as a base64 encoded PNG.
    The payload is a JSON string with the student UUID and school ID.
    """
    payload = {
        "u": student_uuid,
        "s": school_id
    }
    
    # Convert to JSON string
    qr_data = json.dumps(payload)
    
    # Create QR code object
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Generate image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to buffer
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    
    # Convert to base64
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"
