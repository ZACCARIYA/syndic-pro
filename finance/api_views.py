from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Sum, Count
from django.utils import timezone
from .models import User, Document, Depense, Notification, Payment, ResidentReport


@method_decorator(login_required, name='dispatch')
class NavigationStatsAPI(View):
    """API pour les statistiques de navigation en temps réel"""
    
    def get(self, request):
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            return JsonResponse({'error': 'Accès non autorisé'}, status=403)
        
        try:
            # Statistiques de base
            total_residents = User.objects.filter(role='RESIDENT').count()
            total_documents = Document.objects.filter(is_archived=False).count()
            total_expenses = Depense.objects.count()
            
            # Documents en retard
            from django.utils import timezone
            today = timezone.now().date()
            overdue_documents = Document.objects.filter(
                is_paid=False,
                is_archived=False
            )
            overdue_count = sum(1 for doc in overdue_documents if doc.is_overdue)
            
            # Notifications non lues
            unread_notifications = Notification.objects.filter(
                is_read=False,
                is_active=True,
                recipients=request.user
            ).count()
            
            # Signalements de problèmes
            issue_reports = ResidentReport.objects.filter(
                status='NEW'
            ).count()
            
            # Statistiques avancées
            current_month = today.replace(day=1)
            
            # Documents ce mois
            documents_this_month = Document.objects.filter(
                created_at__gte=current_month,
                is_archived=False
            ).count()
            
            # Paiements ce mois
            payments_this_month = Payment.objects.filter(
                payment_date__gte=current_month
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Dépenses ce mois
            expenses_this_month = Depense.objects.filter(
                date_depense__gte=current_month
            ).aggregate(total=Sum('montant'))['total'] or 0
            
            # Nouveaux résidents ce mois
            recent_residents = User.objects.filter(
                role='RESIDENT',
                date_joined__gte=current_month
            ).count()
            
            return JsonResponse({
                'total_residents': total_residents,
                'total_documents': total_documents,
                'total_expenses': total_expenses,
                'overdue_count': overdue_count,
                'unread_notifications': unread_notifications,
                'issue_reports': issue_reports,
                'documents_this_month': documents_this_month,
                'payments_this_month': float(payments_this_month),
                'expenses_this_month': float(expenses_this_month),
                'recent_residents': recent_residents,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
