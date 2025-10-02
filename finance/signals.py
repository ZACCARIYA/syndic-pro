from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Document, Payment, Notification, OperationLog, Depense
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone


def send_email_to_resident(subject: str, message: str, recipient_email: str) -> int:
    """Send an email to a resident using configured SMTP settings.

    Returns number of successfully delivered messages (0 or 1).
    """
    return send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        recipient_list=[recipient_email],
        fail_silently=False,
    )


@receiver(post_save, sender=Document)
def send_document_email(sender, instance: Document, created: bool, **kwargs):
    """Notify resident by email when a new document is created (HTML template)."""
    if not created:
        return
    if not instance.resident or not instance.resident.email:
        return

    # Construire un lien vers le document si possible
    try:
        from django.urls import reverse
        base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        link = base_url + reverse('finance:document_detail', args=[instance.pk])
    except Exception:
        link = None

    subject = f"Nouveau document: {instance.title}"
    context = {
        'subject': subject,
        'resident_name': (instance.resident.get_full_name() or instance.resident.username),
        'document_type': instance.get_document_type_display(),
        'amount': instance.amount,
        'date': instance.date,
        'message': getattr(instance, 'description', '') or '',
        'link': link,
        'intro_text': "Un nouveau document a été ajouté à votre espace.",
    }
    try:
        from .emails import send_templated_email
        send_templated_email(
            subject=subject,
            to_email=instance.resident.email,
            template_name='emails/document_added.html',
            context=context,
        )
    except Exception:
        # Fallback simple texte si le HTML échoue
        try:
            message = (
                f"Bonjour {context['resident_name']},\n\n"
                f"Un nouveau document a été ajouté à votre espace.\n"
                f"Type: {context['document_type']}\nMontant: {context['amount']} DH\nDate: {context['date']}\n"
                f"Lien: {link or ''}"
            )
            send_email_to_resident(subject, message, instance.resident.email)
        except Exception:
            pass
    try:
        OperationLog.objects.create(
            action='DOCUMENT_CREATED',
            actor=instance.uploaded_by,
            target_id=str(instance.pk),
            target_type='Document',
            meta={'title': instance.title, 'resident': instance.resident_id}
        )
    except Exception:
        pass


@receiver(post_save, sender=Document)
def create_in_app_notification_for_document(sender, instance: Document, created: bool, **kwargs):
    """Create in-app notification when a document is uploaded for a resident."""
    if not created:
        return
    try:
        notif = Notification.objects.create(
            title=f"Nouveau document: {instance.title}",
            message=f"Type: {instance.get_document_type_display()} • Montant: {instance.amount} DH • Date: {instance.date}",
            notification_type="DOCUMENT_UPLOADED",
            priority="MEDIUM",
            sender=instance.uploaded_by,
            is_active=True,
        )
        notif.recipients.add(instance.resident)
    except Exception:
        # Fail-safe: do not crash on notification creation
        pass


@receiver(post_save, sender=Payment)
def notify_syndic_on_payment(sender, instance: Payment, created: bool, **kwargs):
    """When a resident records a payment, notify syndic via in-app (and email if available)."""
    if not created:
        return
    document = instance.document
    syndic_users = []
    if document:
        # Prefer the uploader as a target syndic
        if document.uploaded_by and document.uploaded_by.role in ["SYNDIC", "SUPERADMIN"]:
            syndic_users = [document.uploaded_by]
    
    # Fallback: notify all staff (syndic/superadmin)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not syndic_users:
        syndic_users = list(User.objects.filter(role__in=["SYNDIC", "SUPERADMIN"]))

    # Create in-app notification
    try:
        title = "Paiement reçu"
        message = f"Montant: {instance.amount} DH • Date: {instance.payment_date} • Méthode: {instance.get_payment_method_display()}"
        notif = Notification.objects.create(
            title=title,
            message=message,
            notification_type="GENERAL_ANNOUNCEMENT",
            priority="HIGH",
            sender=document.resident if document else None,
            is_active=True,
        )
        notif.recipients.add(*syndic_users)
    except Exception:
        pass

    # Optional: send email to primary syndic
    try:
        primary = syndic_users[0]
        if primary and primary.email:
            send_email_to_resident(
                subject="Paiement reçu",
                message=f"Un paiement a été enregistré. {message}",
                recipient_email=primary.email,
            )
    except Exception:
        pass




@receiver(post_save, sender=Depense)
def notify_residents_on_grosse_depense(sender, instance: Depense, created: bool, **kwargs):
    """Notifier tous les résidents quand une grosse dépense est ajoutée."""
    if not created or not instance.is_grosse_depense:
        return
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Récupérer tous les résidents
    residents = User.objects.filter(role='RESIDENT')
    
    if not residents.exists():
        return
    
    try:
        # Créer la notification in-app
        notif = Notification.objects.create(
            title="Nouvelle dépense importante",
            message=f"{instance.titre} • {instance.get_categorie_display()} • {instance.montant} DH • {instance.date_depense}",
            notification_type="GENERAL_ANNOUNCEMENT",
            priority="HIGH",
            sender=instance.ajoute_par,
            is_active=True,
        )
        notif.recipients.add(*residents)
        
        # Envoyer un email à tous les résidents (optionnel)
        for resident in residents:
            if resident.email:
                subject = "Nouvelle dépense importante pour l'immeuble"
                message = (
                    f"Bonjour {resident.get_full_name() or resident.username},\n\n"
                    f"Une nouvelle dépense importante a été enregistrée :\n\n"
                    f"Titre: {instance.titre}\n"
                    f"Catégorie: {instance.get_categorie_display()}\n"
                    f"Montant: {instance.montant} DH\n"
                    f"Date: {instance.date_depense}\n"
                    f"Description: {instance.description or 'Aucune description'}\n\n"
                    f"Connectez-vous pour consulter le détail des dépenses."
                )
                send_email_to_resident(subject, message, resident.email)
                
    except Exception as e:
        # Log l'erreur mais ne pas planter
        print(f"Erreur lors de l'envoi des notifications de dépense: {e}")
        pass





