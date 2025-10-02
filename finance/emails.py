from typing import Dict, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    return getattr(settings, name, default)


def send_templated_email(
    *,
    subject: str,
    to_email: str,
    template_name: str,
    context: Dict,
) -> int:
    from_email = (
        get_setting("DEFAULT_FROM_EMAIL")
        or get_setting("EMAIL_HOST_USER")
        or "no-reply@syndic.local"
    )

    email_context = {
        "app_name": get_setting("APP_NAME", "SyndicPro"),
        "logo_url": get_setting("EMAIL_LOGO_URL", None),
        "syndic_name": get_setting("SYNDIC_NAME", "SyndicPro"),
        "syndic_contact_email": get_setting("SYNDIC_CONTACT_EMAIL", from_email),
        **context,
    }

    html_content = render_to_string(template_name, email_context)
    text_content = render_to_string(
        "emails/text_fallback.txt",
        email_context,
    )

    msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, to=[to_email])
    msg.attach_alternative(html_content, "text/html")
    return msg.send(fail_silently=False)
