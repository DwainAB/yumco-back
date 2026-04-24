from app.services.email_service import build_base64_attachment, send_email
from app.services.receipt_service import generate_receipt


def _items_html(order) -> str:
    rows = ""
    for item in order.items:
        if item.parent_order_item_id is not None:
            rows += f"<tr><td style='padding:2px 8px 2px 24px;color:#555;font-size:13px;'>› {item.name}</td><td></td></tr>"
        else:
            rows += (
                f"<tr>"
                f"<td style='padding:4px 8px;'>{item.quantity}x {item.name}</td>"
                f"<td style='padding:4px 8px;text-align:right;'>{float(item.subtotal):.2f} €</td>"
                f"</tr>"
            )
    return rows


def _base_template(restaurant_name: str, title: str, body_html: str, order) -> str:
    items_rows = _items_html(order)
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#222;">
      <div style="background:#111;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;">{restaurant_name}</h2>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
        <h3 style="margin-top:0;">{title}</h3>
        {body_html}
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
        <p style="font-size:13px;font-weight:bold;margin-bottom:4px;">Récapitulatif de votre commande :</p>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          {items_rows}
          <tr style="border-top:1px solid #eee;">
            <td style="padding:8px;font-weight:bold;">Total</td>
            <td style="padding:8px;text-align:right;font-weight:bold;">{float(order.amount_total):.2f} €</td>
          </tr>
        </table>
        <p style="font-size:11px;color:#aaa;margin-top:32px;text-align:center;">Propulsé par Yumco</p>
      </div>
    </div>
    """


async def send_order_confirmed(order, restaurant):
    if not order.customer or not order.customer.email:
        return
    body = f"""
    <p>Bonjour <strong>{order.customer.first_name}</strong>,</p>
    <p>Nous avons bien reçu votre commande <strong>{order.order_number}</strong> et nous la traitons dès maintenant.</p>
    <p>Nous vous tiendrons informé de l'avancement de votre commande.</p>
    <p>Merci pour votre confiance !</p>
    <p><em>L'équipe {restaurant.name}</em></p>
    """
    html = _base_template(restaurant.name, "Commande reçue ✓", body, order)
    await send_email(
        to=order.customer.email,
        subject=f"{restaurant.name} – Commande {order.order_number} confirmée",
        body=html
    )


async def send_order_preparing(order, restaurant, preparation_time: int | None = None):
    if not order.customer or not order.customer.email:
        return
    if preparation_time is None and restaurant.config:
        preparation_time = restaurant.config.preparation_time
    if preparation_time:
        display_time = "1h" if preparation_time >= 60 else f"{preparation_time} minutes"
        time_line = f"<p>Temps de préparation estimé : <strong>{display_time}</strong></p>"
    else:
        time_line = ""
    body = f"""
    <p>Bonjour <strong>{order.customer.first_name}</strong>,</p>
    <p>Bonne nouvelle ! Votre commande <strong>{order.order_number}</strong> est actuellement en cours de préparation.</p>
    {time_line}
    <p>Nous faisons tout pour vous la préparer dans les meilleurs délais.</p>
    <p><em>L'équipe {restaurant.name}</em></p>
    """
    html = _base_template(restaurant.name, "Votre commande est en préparation 👨‍🍳", body, order)
    await send_email(
        to=order.customer.email,
        subject=f"{restaurant.name} – Commande {order.order_number} en préparation",
        body=html
    )


async def send_order_completed(order, restaurant):
    if not order.customer or not order.customer.email:
        return
    if order.type == "pickup":
        action = "Vous pouvez dès à présent venir récupérer votre commande à notre adresse."
        subtitle = "Votre commande est prête à être récupérée 🛍️"
    else:
        action = "Votre commande est en route et sera livrée chez vous très prochainement."
        subtitle = "Votre commande est en route 🚗"
    body = f"""
    <p>Bonjour <strong>{order.customer.first_name}</strong>,</p>
    <p>Votre commande <strong>{order.order_number}</strong> est prête !</p>
    <p>{action}</p>
    <p>Merci et à bientôt !</p>
    <p><em>L'équipe {restaurant.name}</em></p>
    """
    html = _base_template(restaurant.name, subtitle, body, order)
    await send_email(
        to=order.customer.email,
        subject=f"{restaurant.name} – Commande {order.order_number} prête",
        body=html
    )


async def send_order_cancelled(order, restaurant):
    if not order.customer or not order.customer.email:
        return
    body = f"""
    <p>Bonjour <strong>{order.customer.first_name}</strong>,</p>
    <p>Nous sommes navrés de vous informer que votre commande <strong>{order.order_number}</strong> a été annulée.</p>
    <p>Si vous avez des questions, n'hésitez pas à nous contacter directement.</p>
    <p>Nous espérons vous revoir très prochainement.</p>
    <p><em>L'équipe {restaurant.name}</em></p>
    """
    html = _base_template(restaurant.name, "Commande annulée", body, order)
    await send_email(
        to=order.customer.email,
        subject=f"{restaurant.name} – Commande {order.order_number} annulée",
        body=html
    )


async def send_order_receipt(order, restaurant, to_email: str):
    customer_name = order.customer.first_name if order.customer else "client"
    body = f"""
    <p>Bonjour <strong>{customer_name}</strong>,</p>
    <p>Veuillez trouver en pièce jointe le reçu de votre commande <strong>{order.order_number}</strong>.</p>
    <p><em>L'équipe {restaurant.name}</em></p>
    """
    html = _base_template(restaurant.name, "Votre reçu de commande", body, order)
    pdf = generate_receipt(order, restaurant)
    filename = f"ticket_{order.order_number.replace('#', '')}.pdf"
    attachment = build_base64_attachment(filename, pdf.getvalue())
    await send_email(
        to=to_email,
        subject=f"{restaurant.name} – Reçu de la commande {order.order_number}",
        body=html,
        attachments=[attachment],
    )
