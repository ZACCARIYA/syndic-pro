from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Vérification quotidienne automatique des impayés (à exécuter via cron)'

    def handle(self, *args, **options):
        """
        Commande à exécuter quotidiennement via cron pour détecter automatiquement les impayés
        
        Pour configurer sur le serveur, ajoutez à votre crontab :
        0 9 * * * cd /path/to/project && python manage.py daily_overdue_check
        
        Cela exécutera la vérification tous les jours à 9h du matin
        """
        
        self.stdout.write(
            self.style.SUCCESS(f'🕘 VÉRIFICATION QUOTIDIENNE DES IMPAYÉS - {timezone.now().strftime("%Y-%m-%d %H:%M")}')
        )
        
        try:
            # Exécuter la détection des impayés
            call_command('detect_overdue_payments')
            
            self.stdout.write(
                self.style.SUCCESS('✅ Vérification quotidienne terminée avec succès')
            )
            
            # Log pour suivi
            logger.info(f"Vérification quotidienne des impayés exécutée avec succès - {timezone.now()}")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Erreur lors de la vérification quotidienne: {e}')
            )
            logger.error(f"Erreur vérification quotidienne des impayés: {e}")
            raise
