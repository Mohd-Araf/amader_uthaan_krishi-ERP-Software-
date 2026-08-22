import datetime
from email.utils import formataddr

from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import render, redirect

from amader_uthaan_krishi import settings
from apps.products.models import Product

def home(request):

    products = Product.objects.all().order_by('?')[:8]

    return render(request, 'home.html', {
        'products': products
    })
from django.shortcuts import render


def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        user_email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()
        if not name or not user_email or not subject or not message_text:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'contact.html')
        current_time = datetime.datetime.now().strftime('%d %b %Y, %I:%M %p')
        # formataddr স্বয়ংক্রিয়ভাবে "Md. Rakib" <email> সঠিকভাবে কোটেশন দিয়ে হ্যান্ডেল করে
        dynamic_from_email = formataddr((name, user_email))
        # HTML Email Template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>New Contact Message</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #334155;">

            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 30px 15px;">
                <tr>
                    <td align="center">
                        <table role="presentation" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;" cellspacing="0" cellpadding="0">

                            <!-- BRAND HEADER -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #047857 0%, #10b981 100%); padding: 30px 25px; text-align: center;">
                                    <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase;">
                                        Amader Uthaan Krishi ERP
                                    </h1>
                                    <p style="color: #ecfdf5; margin: 6px 0 0 0; font-size: 13.5px; font-weight: 500;">
                                        Customer Inquiry & Contact Form
                                    </p>
                                </td>
                            </tr>
                            <!-- CONTENT AREA -->
                            <tr>
                                <td style="padding: 30px 25px;">
                                    <div style="display: inline-block; background-color: #ecfdf5; color: #065f46; font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 20px; border: 1px solid #a7f3d0; margin-bottom: 18px;">
                                        📩 New Message Received
                                    </div>
                                    <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #0f172a; font-weight: 700;">
                                        {subject}
                                    </h2>
                                    <!-- SENDER DETAILS -->
                                    <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse: collapse; margin-bottom: 22px; background-color: #f8fafc; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
                                        <tr>
                                            <td style="padding: 10px 14px; font-size: 13px; font-weight: 600; color: #64748b; width: 30%; border-bottom: 1px solid #e2e8f0;">Sender Name</td>
                                            <td style="padding: 10px 14px; font-size: 13.5px; font-weight: 700; color: #1e293b; border-bottom: 1px solid #e2e8f0;">{name}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 10px 14px; font-size: 13px; font-weight: 600; color: #64748b; border-bottom: 1px solid #e2e8f0;">Sender Email</td>
                                            <td style="padding: 10px 14px; font-size: 13.5px; color: #0284c7; font-weight: 600; border-bottom: 1px solid #e2e8f0;">
                                                <a href="mailto:{user_email}" style="color: #0284c7; text-decoration: none;">{user_email}</a>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 10px 14px; font-size: 13px; font-weight: 600; color: #64748b;">Received At</td>
                                            <td style="padding: 10px 14px; font-size: 13px; color: #475569;">{current_time}</td>
                                        </tr>
                                    </table>
                                    <!-- MESSAGE BOX -->
                                    <div style="margin-bottom: 25px;">
                                        <p style="font-size: 13px; font-weight: 700; color: #475569; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                            Message Content:
                                        </p>
                                        <div style="background-color: #fdfdfd; border-left: 4px solid #10b981; padding: 16px; border-radius: 0 8px 8px 0; font-size: 14.5px; line-height: 1.6; color: #334155; border-top: 1px solid #f1f5f9; border-right: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9;">
                                            {message_text.replace(chr(10), '<br>')}
                                        </div>
                                    </div>
                                    <!-- REPLY BUTTON -->
                                    <div style="text-align: center; margin-top: 25px; margin-bottom: 10px;">
                                        <a href="mailto:{user_email}?subject=Re: {subject}" style="background-color: #10b981; color: #ffffff; padding: 12px 26px; border-radius: 6px; font-size: 14px; font-weight: 700; text-decoration: none; display: inline-block;">
                                            ✉️ Reply to {name}
                                        </a>
                                    </div>
                                </td>
                            </tr>
                            <!-- FOOTER -->
                            <tr>
                                <td style="background-color: #f8fafc; padding: 18px 25px; text-align: center; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8;">
                                    <p style="margin: 0 0 4px 0;">
                                        This notification was automatically sent from the Contact Us form on <strong>Amader Uthaan Krishi ERP</strong>.
                                    </p>
                                    <p style="margin: 0;">
                                        © {datetime.datetime.now().year} Amader Uthaan Krishi. All rights reserved.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        try:
            email = EmailMessage(
                subject=f"[{name}] {subject}",
                body=html_content,
                from_email=dynamic_from_email,
                to=['22201138@uap-bd.edu'],
                reply_to=[user_email],
            )
            email.content_subtype = "html"
            email.send(fail_silently=False)
            messages.success(request,
                             'Thank you! Your message has been sent successfully. We will get back to you soon.')
            return redirect('contact')
        except Exception as e:
            messages.error(request, f'Failed to send message: {str(e)}')
    return render(request, 'contact.html')
def about(request):
    return render(request, 'about.html')