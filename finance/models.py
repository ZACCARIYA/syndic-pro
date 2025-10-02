from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.mail import send_mail
import os
from decimal import Decimal
from datetime import timedelta

User = get_user_model()


class OperationLog(models.Model):
    """Unified history log for important actions."""
    ACTIONS = [
        ("DOCUMENT_CREATED", "Document créé"),
        ("DOCUMENT_ARCHIVED", "Document archivé"),
        ("PAYMENT_CREATED", "Paiement enregistré"),
        ("EVENT_CREATED", "Événement créé"),
    ]
    action = models.CharField(max_length=40, choices=ACTIONS)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_type = models.CharField(max_length=40, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

class Event(models.Model):
    """Shared calendar events (meetings, deadlines, other)."""
    EVENT_TYPES = [
        ("MEETING", "Réunion de copropriété"),
        ("PAYMENT_DEADLINE", "Date limite de paiement"),
        ("OTHER", "Autre"),
    ]

    AUDIENCE = [
        ("ALL_RESIDENTS", "Tous les résidents"),
        ("SPECIFIC", "Résidents sélectionnés"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default="OTHER")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    audience = models.CharField(max_length=20, choices=AUDIENCE, default="ALL_RESIDENTS")
    participants = models.ManyToManyField(User, blank=True, related_name="events",
        limit_choices_to={'role': 'RESIDENT'})
    reminder_minutes_before = models.PositiveIntegerField(default=120,
        help_text="Envoyer une notification X minutes avant l'événement")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_events", limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_at"]

    def __str__(self):
        return f"{self.title} - {self.start_at:%Y-%m-%d %H:%M}"

class ResidentReport(models.Model):
    """General reports submitted by residents for various issues and feedback."""
    REPORT_CATEGORIES = [
        ("MAINTENANCE", "Entretien / Réparation"),
        ("SECURITY", "Sécurité / Surveillance"),
        ("COMMUNITY", "Communauté / Voisinage"),
        ("CLEANLINESS", "Propreté / Nettoyage"),
        ("NOISE", "Bruit / Troubles"),
        ("UTILITIES", "Services / Équipements"),
        ("OTHER", "Autre"),
    ]

    STATUS = [
        ("NEW", "Nouveau"),
        ("IN_PROGRESS", "En cours"),
        ("RESOLVED", "Résolu"),
        ("ARCHIVED", "Archivé"),
    ]

    resident = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="resident_reports",
        limit_choices_to={"role": "RESIDENT"},
    )
    title = models.CharField(max_length=200, verbose_name="Titre du rapport")
    description = models.TextField(verbose_name="Description détaillée", default="Description non fournie")
    category = models.CharField(max_length=20, choices=REPORT_CATEGORIES, default="OTHER", verbose_name="Catégorie")
    photo = models.ImageField(upload_to="reports/%Y/%m/", null=True, blank=True, verbose_name="Photo (optionnelle)")
    location = models.CharField(max_length=200, blank=True, null=True, verbose_name="Localisation (optionnelle)")
    status = models.CharField(max_length=20, choices=STATUS, default="NEW", verbose_name="Statut")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_reports",
        limit_choices_to={"role__in": ["SUPERADMIN", "SYNDIC"]},
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Rapport de résident"
        verbose_name_plural = "Rapports de résidents"

    def __str__(self):
        return f"{self.title} - {self.resident.username}"

    def get_status_display_color(self):
        """Return Bootstrap color class for status."""
        colors = {
            "NEW": "primary",
            "IN_PROGRESS": "warning", 
            "RESOLVED": "success",
            "ARCHIVED": "secondary"
        }
        return colors.get(self.status, "secondary")


class ReportComment(models.Model):
    """Comments on reports by syndics and residents."""
    report = models.ForeignKey(ResidentReport, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="report_comments")
    comment = models.TextField(verbose_name="Commentaire")
    is_internal = models.BooleanField(default=False, verbose_name="Commentaire interne")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Commentaire de rapport"
        verbose_name_plural = "Commentaires de rapports"

    def __str__(self):
        return f"Commentaire sur {self.report.title} par {self.author.username}"


class Document(models.Model):
    """Documents uploaded by syndic for residents"""
    DOCUMENT_TYPES = [
        ('INVOICE', 'Facture'),
        ('NOTICE', 'Avis'),
        ('REMINDER', 'Rappel'),
        ('LEGAL', 'Document légal'),
        ('OTHER', 'Autre'),
    ]
    
    title = models.CharField(max_length=200, help_text="Titre du document")
    file = models.FileField(upload_to='documents/%Y/%m/', help_text="Fichier du document")
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Montant en DH")
    date = models.DateField(default=timezone.now, help_text="Date du document")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, default='INVOICE')
    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents', 
                                limit_choices_to={'role': 'RESIDENT'})
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_documents',
                                   limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    description = models.TextField(blank=True, help_text="Description du document")
    is_paid = models.BooleanField(default=False, help_text="Document payé")
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.resident.username} - {self.amount} DH"

    @property
    def is_overdue(self):
        """Check if document is overdue (more than 30 days old and not paid)"""
        if self.is_paid:
            return False
        return (timezone.now().date() - self.date).days > 30

    @property
    def days_overdue(self):
        """Number of days overdue"""
        if self.is_paid:
            return 0
        return max(0, (timezone.now().date() - self.date).days - 30)

    @property
    def status(self):
        """Document status based on payment and due date"""
        if self.is_paid:
            return 'paid'
        elif self.is_overdue:
            days = self.days_overdue
            if days >= 90:
                return 'critical'
            elif days >= 60:
                return 'overdue_60'
            elif days >= 30:
                return 'overdue_30'
            else:
                return 'overdue'
        else:
            return 'pending'

    @property
    def due_date(self):
        """Calculate due date (30 days after document date)"""
        return self.date + timezone.timedelta(days=30)

    @property
    def is_due_soon(self):
        """Check if document is due within 7 days"""
        if self.is_paid:
            return False
        days_until_due = (self.due_date - timezone.now().date()).days
        return 0 <= days_until_due <= 7

    @property
    def urgency_level(self):
        """Get urgency level for notifications"""
        if self.is_paid:
            return 'none'
        elif self.days_overdue >= 90:
            return 'critical'
        elif self.days_overdue >= 60:
            return 'high'
        elif self.days_overdue >= 30:
            return 'medium'
        elif self.is_due_soon:
            return 'low'
        else:
            return 'none'

    def get_reminder_message(self, for_syndic=False):
        """Generate reminder message for notifications"""
        if for_syndic:
            return (
                f"Impayé détecté pour {self.resident.get_full_name() or self.resident.username}\n"
                f"Document: {self.title}\n"
                f"Montant: {self.amount} DH\n"
                f"Date d'échéance: {self.due_date.strftime('%d/%m/%Y')}\n"
                f"Retard: {self.days_overdue} jours\n"
                f"Appartement: {self.resident.apartment or 'N/A'}"
            )
        else:
            return (
                f"Rappel de paiement pour votre document: {self.title}\n"
                f"Montant à régler: {self.amount} DH\n"
                f"Date d'échéance dépassée: {self.due_date.strftime('%d/%m/%Y')}\n"
                f"Retard: {self.days_overdue} jours\n"
                f"Veuillez régulariser votre situation rapidement."
            )


class Notification(models.Model):
    """Notifications system"""
    NOTIFICATION_TYPES = [
        ("PAYMENT_REMINDER", "Rappel de paiement"),
        ("DOCUMENT_UPLOADED", "Nouveau document"),
        ("GENERAL_ANNOUNCEMENT", "Annonce générale"),
        ("MEETING_NOTICE", "Convocation réunion"),
        ("LEGAL_NOTICE", "Avis légal"),
        ("OTHER", "Autre"),
    ]
    
    PRIORITY_LEVELS = [
        ("LOW", "Faible"),
        ("MEDIUM", "Moyenne"),
        ("HIGH", "Élevée"),
        ("URGENT", "Urgente"),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default="GENERAL_ANNOUNCEMENT")
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default="MEDIUM")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_notifications",
                              limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    recipients = models.ManyToManyField(User, related_name="received_notifications",
                                       limit_choices_to={'role': 'RESIDENT'})
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.get_notification_type_display()}"

    def mark_as_read(self, user):
        """Mark notification as read for a specific user"""
        if user in self.recipients.all():
            self.is_read = True
            self.read_at = timezone.now()
            self.save()


class Payment(models.Model):
    """Payment records for documents"""
    PAYMENT_METHODS = [
        ('CASH', 'Espèces'),
        ('BANK_TRANSFER', 'Virement bancaire'),
        ('CHECK', 'Chèque'),
        ('CARD', 'Carte bancaire'),
        ('OTHER', 'Autre'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    payment_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    payment_proof = models.ImageField(upload_to='payment_proofs/%Y/%m/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='verified_payments',
                                   limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Paiement {self.document.title} - {self.amount} DH - {self.payment_date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update document payment status
        total_paid = self.document.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        self.document.is_paid = total_paid >= self.document.amount
        self.document.save()


class Depense(models.Model):
    """Dépenses liées à l'immeuble gérées par le syndic"""
    CATEGORIES = [
        ('ENTRETIEN', 'Entretien'),
        ('REPARATION', 'Réparation'),
        ('FACTURE', 'Facture'),
        ('AUTRE', 'Autre'),
    ]
    
    titre = models.CharField(max_length=200, help_text="Titre de la dépense")
    description = models.TextField(blank=True, help_text="Détails de la dépense")
    montant = models.DecimalField(max_digits=10, decimal_places=2, help_text="Montant en DH")
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='AUTRE')
    date_depense = models.DateField(default=timezone.now, help_text="Date de la dépense")
    ajoute_par = models.ForeignKey(User, on_delete=models.CASCADE, related_name='depenses_ajoutees',
                                  limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_depense', '-created_at']
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"

    def __str__(self):
        return f"{self.titre} - {self.montant} DH - {self.date_depense}"

    @property
    def is_grosse_depense(self):
        """Vérifie si c'est une grosse dépense (> 1000 DH par défaut)"""
        seuil = Decimal('1000.00')  # Seuil configurable
        return self.montant > seuil


class ResidentStatus(models.Model):
    """Track resident payment status"""
    resident = models.OneToOneField(User, on_delete=models.CASCADE, related_name='status',
                                   limit_choices_to={'role': 'RESIDENT'})
    total_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Statut du résident"
        verbose_name_plural = "Statuts des résidents"

    def __str__(self):
        return f"Statut {self.resident.username} - {self.total_due} DH dus"

    @property
    def balance(self):
        """Current balance (positive = owes money, negative = credit)"""
        return self.total_due - self.total_paid

    @property
    def status_category(self):
        """Categorize resident status"""
        if self.balance <= 0:
            return 'up_to_date'
        elif self.balance <= 100:
            return 'pending'
        elif self.balance <= 500:
            return 'overdue'
        else:
            return 'critical'

    def update_totals(self):
        """Update totals from documents and payments"""
        # Calculate total due from unpaid documents
        unpaid_docs = self.resident.documents.filter(is_paid=False)
        self.total_due = sum(doc.amount for doc in unpaid_docs)
        
        # Calculate total paid from all payments
        all_payments = Payment.objects.filter(document__resident=self.resident)
        self.total_paid = sum(payment.amount for payment in all_payments)
        
        self.save()


class OverdueNotificationLog(models.Model):
    """Log des notifications d'impayés envoyées pour éviter les doublons"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='overdue_notifications')
    notification_type = models.CharField(max_length=20, choices=[
        ('REMINDER_7', 'Rappel 7 jours'),
        ('OVERDUE_30', 'Impayé 30 jours'),
        ('OVERDUE_60', 'Impayé 60 jours'),
        ('CRITICAL_90', 'Critique 90 jours'),
    ])
    sent_to_resident = models.BooleanField(default=False)
    sent_to_syndic = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['document', 'notification_type']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.document.title}"


class ChatbotFAQ(models.Model):
    """Questions fréquentes pour l'assistant virtuel"""
    CATEGORIES = [
        ('PAIEMENT', 'Paiements et Factures'),
        ('CHARGES', 'Charges de Copropriété'),
        ('ENTRETIEN', 'Entretien et Réparations'),
        ('REGLEMENT', 'Règlement Intérieur'),
        ('CONTACT', 'Contact et Démarches'),
        ('GENERAL', 'Questions Générales'),
    ]
    
    question = models.CharField(max_length=300, help_text="Question fréquente")
    keywords = models.TextField(help_text="Mots-clés séparés par des virgules (pour détection automatique)")
    answer = models.TextField(help_text="Réponse automatique")
    category = models.CharField(max_length=20, choices=CATEGORIES, default='GENERAL')
    is_active = models.BooleanField(default=True)
    usage_count = models.PositiveIntegerField(default=0, help_text="Nombre d'utilisations")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_faqs',
                                  limit_choices_to={'role__in': ['SUPERADMIN', 'SYNDIC']})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-usage_count', '-created_at']
        verbose_name = "Question Fréquente"
        verbose_name_plural = "Questions Fréquentes"
    
    def __str__(self):
        return f"{self.question[:50]}... ({self.get_category_display()})"
    
    def increment_usage(self):
        """Incrémenter le compteur d'utilisation"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])


class ChatbotConversation(models.Model):
    """Conversations avec l'assistant virtuel"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chatbot_conversations')
    session_id = models.CharField(max_length=100, help_text="ID de session pour grouper les messages")
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"Conversation {self.user.username} - {self.started_at.strftime('%d/%m/%Y %H:%M')}"


class ChatbotMessage(models.Model):
    """Messages dans les conversations avec le chatbot"""
    MESSAGE_TYPES = [
        ('USER', 'Message Utilisateur'),
        ('BOT', 'Réponse Bot'),
        ('FAQ', 'Réponse FAQ Automatique'),
        ('HUMAN', 'Réponse Humaine (Syndic)'),
    ]
    
    conversation = models.ForeignKey(ChatbotConversation, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    content = models.TextField()
    faq_used = models.ForeignKey(ChatbotFAQ, on_delete=models.SET_NULL, null=True, blank=True,
                                help_text="FAQ utilisée pour la réponse automatique")
    created_at = models.DateTimeField(auto_now_add=True)
    is_helpful = models.BooleanField(null=True, blank=True, help_text="L'utilisateur a-t-il trouvé la réponse utile?")
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.get_message_type_display()} - {self.content[:50]}..."


# Mock functions for SMS and Email
def send_sms(phone_number, message):
    """Mock SMS sending function - logs message instead of sending"""
    print(f"[SMS MOCK] To: {phone_number}")
    print(f"[SMS MOCK] Message: {message}")
    print(f"[SMS MOCK] Status: Sent (Mock)")
    return True


def send_email(recipient_email, subject, message, html_message=None):
    """Email sender. Uses real SMTP if SEND_REAL_EMAILS=True, otherwise logs (mock)."""
    try:
        if os.getenv("SEND_REAL_EMAILS", "False") == "True":
            sent = send_mail(
                subject=subject,
                message=message or "",
                from_email=None,  # falls back to DEFAULT_FROM_EMAIL
                recipient_list=[recipient_email],
                fail_silently=False,
                html_message=html_message,
            )
            print(f"[EMAIL SMTP] To: {recipient_email} -> sent={sent}")
            return bool(sent)
    except Exception as e:
        print(f"[EMAIL SMTP] Error sending to {recipient_email}: {e}")
        return False

    # Mock path
    print(f"[EMAIL MOCK] To: {recipient_email}")
    print(f"[EMAIL MOCK] Subject: {subject}")
    print(f"[EMAIL MOCK] Message: {message}")
    if html_message:
        print(f"[EMAIL MOCK] HTML: {html_message}")
    print(f"[EMAIL MOCK] Status: Sent (Mock)")
    return True