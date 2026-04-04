from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from models import db, Product, ProductCategory, Order, OrderItem, PaymentStatus, PaymentMethod
from decimal import Decimal

market_bp = Blueprint('market', __name__, url_prefix='/market')

@market_bp.route('/')
@login_required
def browse():
    """List all categories and active products."""
    categories = ProductCategory.query.filter_by(school_id=current_user.school_id).all()
    products = Product.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    return render_template('market/browse.html', categories=categories, products=products)

@market_bp.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    """View specific item details."""
    product = Product.query.get_or_404(product_id)
    if product.school_id != current_user.school_id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('market.browse'))
    return render_template('market/product.html', product=product)

@market_bp.route('/order/create', methods=['POST'])
@login_required
def create_order():
    """Build an order from cart items."""
    data = request.json
    cart_items = data.get('items', []) # [{'product_id': 1, 'quantity': 2}]
    
    if not cart_items:
        return jsonify({"status": "error", "message": "Cart is empty"}), 400
        
    total_amount = Decimal('0.00')
    new_order = Order(
        school_id=current_user.school_id,
        user_id=current_user.id,
        total_amount=0,
        status=PaymentStatus.PENDING
    )
    db.session.add(new_order)
    db.session.flush()
    
    for item in cart_items:
        p = Product.query.get(item['product_id'])
        if p and p.stock_quantity >= item['quantity']:
            subtotal = p.base_price * item['quantity']
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=p.id,
                quantity=item['quantity'],
                unit_price=p.base_price,
                subtotal=subtotal
            )
            db.session.add(order_item)
            total_amount += subtotal
            p.stock_quantity -= item['quantity'] # Reserve stock
        else:
            return jsonify({"status": "error", "message": f"Insufficent stock for {p.name}"}), 400
            
    new_order.total_amount = total_amount
    db.session.commit()
    
    # Generate Paystack Link (Placeholder)
    pay_link = f"https://paystack.com/pay/{new_order.id}_ORDER_{current_user.school_id}"
    
    return jsonify({
        "status": "success",
        "order_id": new_order.id,
        "payment_url": pay_link,
        "total": float(total_amount)
    })

@market_bp.route('/my-orders')
@login_required
def my_orders():
    """History of personal transactions."""
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('market/orders.html', orders=orders)
