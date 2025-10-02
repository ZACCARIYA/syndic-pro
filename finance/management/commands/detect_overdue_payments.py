from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from finance.models import Document, Notification, OverdueNotificationLog, send_email
from django.contrib.auth import get_user_model
from datetime import timedelta

User = get_user_model()


class Command(BaseCommand):
    help = 'Détecte automatiquement les impayés et envoie des notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mode test - affiche les actions sans les exécuter',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force l\'envoi même si déjà envoyé',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('🔍 DÉTECTION AUTOMATIQUE DES IMPAYÉS')
        )
        self.stdout.write('=' * 60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODE TEST ACTIVÉ - Aucune notification ne sera envoyée')
            )
        
        today = timezone.now().date()
        
        # Récupérer tous les documents non payés et non archivés
        unpaid_documents = Document.objects.filter(
            is_paid=False,
            is_archived=False
        ).select_related('resident')
        
        self.stdout.write(f"\n📋 {unpaid_documents.count()} documents non payés trouvés")
        
        notifications_sent = 0
        
        for document in unpaid_documents:
            days_since_due = (today - document.due_date).days
            
            # Déterminer le type de notification nécessaire
            notification_type = None
            priority = "MEDIUM"
            
            # Rappel 7 jours avant échéance
            days_until_due = (document.due_date - today).days
            if 0 <= days_until_due <= 7:
                notification_type = 'REMINDER_7'
                priority = "LOW"
            # Impayé 30 jours
            elif 30 <= days_since_due < 60:
                notification_type = 'OVERDUE_30'
                priority = "MEDIUM"
            # Impayé 60 jours
            elif 60 <= days_since_due < 90:
                notification_type = 'OVERDUE_60'
                priority = "HIGH"
            # Critique 90+ jours
            elif days_since_due >= 90:
                notification_type = 'CRITICAL_90'
                priority = "URGENT"
            
            if not notification_type:
                continue
            
            # Vérifier si la notification a déjà été envoyée
            if not force:
                existing_log = OverdueNotificationLog.objects.filter(
                    document=document,
                    notification_type=notification_type
                ).first()
                
                if existing_log:
                    continue
            
            self.stdout.write(f"\n📧 Traitement: {document.title}")
            self.stdout.write(f"   Résident: {document.resident.get_full_name() or document.resident.username}")
            self.stdout.write(f"   Montant: {document.amount} DH")
            self.stdout.write(f"   Retard: {days_since_due} jours")
            self.stdout.write(f"   Type: {notification_type}")
            
            if not dry_run:
                try:
                    with transaction.atomic():
                        # Créer la notification pour le résident
                        resident_notification = Notification.objects.create(
                            title=self.get_notification_title(notification_type, False),
                            message=document.get_reminder_message(for_syndic=False),
                            notification_type="PAYMENT_REMINDER",
                            priority=priority,
                            sender=self.get_system_user(),
                            is_active=True,
                        )
                        resident_notification.recipients.add(document.resident)
                        
                        # Créer la notification pour le syndic
                        syndic_notification = Notification.objects.create(
                            title=self.get_notification_title(notification_type, True),
                            message=document.get_reminder_message(for_syndic=True),
                            notification_type="PAYMENT_REMINDER",
                            priority=priority,
                            sender=self.get_system_user(),
                            is_active=True,
                        )
                        
                        # Ajouter tous les syndics comme destinataires
                        syndics = User.objects.filter(role__in=['SUPERADMIN', 'SYNDIC'])
                        syndic_notification.recipients.add(*syndics)
                        
                        # Envoyer des emails
                        sent_to_resident = self.send_email_notification(document, notification_type, False)
                        sent_to_syndic = self.send_email_notification(document, notification_type, True)
                        
                        # Enregistrer le log
                        OverdueNotificationLog.objects.create(
                            document=document,
                            notification_type=notification_type,
                            sent_to_resident=sent_to_resident,
                            sent_to_syndic=sent_to_syndic
                        )
                        
                        notifications_sent += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"   ✅ Notifications envoyées")
                        )
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"   ❌ Erreur: {e}")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f"   🔍 [TEST] Notification {notification_type} serait envoyée")
                )
                notifications_sent += 1
        
        self.stdout.write(f"\n🎯 RÉSUMÉ:")
        self.stdout.write(f"   📧 {notifications_sent} notifications {'envoyées' if not dry_run else 'détectées'}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n💡 Exécutez sans --dry-run pour envoyer les notifications")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n✅ Détection automatique terminée avec succès")
            )

    def get_notification_title(self, notification_type, for_syndic):
        """Générer le titre de la notification"""
        titles = {
            'REMINDER_7': {
                True: "Échéance proche - Document à régler",
                False: "Rappel: Échéance dans 7 jours"
            },
            'OVERDUE_30': {
                True: "Impayé détecté - 30 jours",
                False: "Document en retard - Action requise"
            },
            'OVERDUE_60': {
                True: "Impayé persistant - 60 jours",
                False: "Retard important - Régularisation urgente"
            },
            'CRITICAL_90': {
                True: "Situation critique - 90+ jours d'impayé",
                False: "URGENT: Régularisation immédiate requise"
            }
        }
        return titles.get(notification_type, {}).get(for_syndic, "Notification de paiement")

    def send_email_notification(self, document, notification_type, for_syndic):
        """Envoyer notification par email"""
        try:
            if for_syndic:
                # Envoyer à tous les syndics
                syndics = User.objects.filter(role__in=['SUPERADMIN', 'SYNDIC'])
                for syndic in syndics:
                    if syndic.email:
                        subject = f"🚨 Impayé détecté - {document.resident.get_full_name() or document.resident.username}"
                        message = (
                            f"Bonjour {syndic.get_full_name() or syndic.username},\n\n"
                            f"Un impayé a été détecté dans votre copropriété :\n\n"
                            f"{document.get_reminder_message(for_syndic=True)}\n\n"
                            f"Veuillez effectuer le suivi nécessaire.\n\n"
                            f"Connectez-vous pour plus de détails."
                        )
                        send_email(syndic.email, subject, message)
            else:
                # Envoyer au résident
                if document.resident.email:
                    subject = f"⏰ Rappel de paiement - {document.title}"
                    message = (
                        f"Bonjour {document.resident.get_full_name() or document.resident.username},\n\n"
                        f"{document.get_reminder_message(for_syndic=False)}\n\n"
                        f"Pour éviter des frais supplémentaires, veuillez régulariser votre situation rapidement.\n\n"
                        f"Connectez-vous à votre espace pour effectuer le paiement."
                    )
                    send_email(document.resident.email, subject, message)
            
            return True
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Erreur envoi email: {e}")
            )
            return False

    def get_system_user(self):
        """Récupérer l'utilisateur système pour les notifications automatiques"""
        system_user = User.objects.filter(role='SUPERADMIN').first()
        if not system_user:
            system_user = User.objects.filter(role='SYNDIC').first()
        return system_user
