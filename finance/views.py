from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import get_user_model, logout, authenticate, login
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db.models import Q
from django.core.exceptions import ValidationError
from decimal import Decimal
import json

from .models import Document, Notification, Payment, ResidentStatus, ResidentReport, ReportComment, Event, Depense, ChatbotFAQ, ChatbotConversation, ChatbotMessage, send_sms, send_email

User = get_user_model()


def role_required(allowed_roles):
    """Decorator to check user roles for class-based views"""
    def decorator(view_func):
        def wrapper(self, request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Veuillez vous connecter pour accéder à cette page.")
                return redirect('finance:login')
            if request.user.role not in allowed_roles:
                messages.error(request, "Accès non autorisé.")
                return redirect('finance:home')
            return view_func(self, request, *args, **kwargs)
        return wrapper
    return decorator


class HomeView(TemplateView):
    """Home page - redirects authenticated users to their dashboard"""
    template_name = 'finance/home.html'

    def get(self, request, *args, **kwargs):
        # Redirect authenticated users to their appropriate dashboard
        if request.user.is_authenticated:
            if request.user.role == 'RESIDENT':
                return redirect('finance:resident_dashboard')
            elif request.user.role in ['SYNDIC', 'SUPERADMIN']:
                return redirect('finance:syndic_dashboard')
        
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add some statistics for the home page
        if self.request.user.is_authenticated:
            try:
                if hasattr(self.request.user, 'role'):
                    context['user_role'] = self.request.user.role
                    context['user_name'] = self.request.user.get_full_name() or self.request.user.username
            except:
                pass
        
        return context


class SyndicDashboardView(TemplateView):
    """Dashboard for syndic - shows residents grouped by status"""
    template_name = 'finance/syndic_dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all residents with their status
        residents = User.objects.filter(role='RESIDENT').prefetch_related('status')
        
        # Update status for all residents
        for resident in residents:
            status, created = ResidentStatus.objects.get_or_create(resident=resident)
            status.update_totals()
        
        # Group residents by status
        up_to_date = []
        pending = []
        overdue = []
        critical = []
        
        for resident in residents:
            if hasattr(resident, 'status'):
                status_category = resident.status.status_category
                if status_category == 'up_to_date':
                    up_to_date.append(resident)
                elif status_category == 'pending':
                    pending.append(resident)
                elif status_category == 'overdue':
                    overdue.append(resident)
                else:  # critical
                    critical.append(resident)
        
        # Statistics principales
        total_residents = residents.count()
        total_due = sum(r.status.total_due for r in residents if hasattr(r, 'status'))
        total_paid = sum(r.status.total_paid for r in residents if hasattr(r, 'status'))
        
        # Statistiques avancées
        from django.utils import timezone
        today = timezone.now().date()
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
        
        # Documents en retard
        overdue_documents = Document.objects.filter(
            is_paid=False,
            is_archived=False
        )
        overdue_count = sum(1 for doc in overdue_documents if doc.is_overdue)
        
        # Notifications non lues
        unread_notifications = Notification.objects.filter(
            is_read=False,
            is_active=True,
            recipients=self.request.user
        ).count()
        
        # Recent activities
        recent_documents = Document.objects.select_related('resident').order_by('-created_at')[:5]
        recent_notifications = Notification.objects.filter(is_active=True).order_by('-created_at')[:5]
        recent_reports = ResidentReport.objects.select_related('resident').order_by('-created_at')[:8]
        recent_payments = Payment.objects.select_related('document__resident').order_by('-payment_date')[:5]
        
        # Évolution mensuelle des paiements (6 derniers mois)
        monthly_payments = []
        for i in range(6):
            month_start = (today.replace(day=1) - timezone.timedelta(days=30*i)).replace(day=1)
            month_end = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1) - timezone.timedelta(days=1)
            
            month_total = Payment.objects.filter(
                payment_date__gte=month_start,
                payment_date__lte=month_end
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            monthly_payments.append({
                'month': month_start.strftime('%b %Y'),
                'amount': float(month_total)
            })
        
        monthly_payments.reverse()  # Ordre chronologique
        
        # Sérialiser les données pour JavaScript
        import json
        context['monthly_payments_json'] = json.dumps(monthly_payments)
        
        context.update({
            'up_to_date': up_to_date,
            'pending': pending,
            'overdue': overdue,
            'critical': critical,
            'total_residents': total_residents,
            'total_due': total_due,
            'total_paid': total_paid,
            'recent_residents': recent_residents,
            'documents_this_month': documents_this_month,
            'payments_this_month': payments_this_month,
            'expenses_this_month': expenses_this_month,
            'overdue_count': overdue_count,
            'unread_notifications': unread_notifications,
            'recent_documents': recent_documents,
            'recent_notifications': recent_notifications,
            'recent_reports': recent_reports,
            'recent_payments': recent_payments,
            'monthly_payments': monthly_payments,
        })
        return context


class ResidentDashboardView(TemplateView):
    """Dashboard for residents - shows their own data"""
    template_name = 'finance/resident_dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'RESIDENT':
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get or create resident status
        status, created = ResidentStatus.objects.get_or_create(resident=user)
        status.update_totals()
        
        # Get resident's documents
        documents = user.documents.all().order_by('-date')
        show_archived = self.request.GET.get('archived') == '1'
        if not show_archived:
            documents = documents.filter(is_archived=False)
        
        # Get resident's notifications
        notifications = user.received_notifications.filter(is_active=True).order_by('-created_at')[:10]
        
        # Recent payments
        recent_payments = Payment.objects.filter(document__resident=user).order_by('-payment_date')[:5]
        
        # Get resident's reports
        recent_reports = user.resident_reports.all().order_by('-created_at')[:5]
        
        # Get upcoming events for residents
        from django.db.models import Q
        upcoming_events = Event.objects.filter(
            Q(audience='ALL_RESIDENTS') | Q(participants=user)
        ).filter(start_at__gte=timezone.now()).order_by('start_at')[:5]
        
        context.update({
            'status': status,
            'documents': documents,
            'notifications': notifications,
            'recent_payments': recent_payments,
            'recent_reports': recent_reports,
            'upcoming_events': upcoming_events,
        })
        return context


class ResidentManagementView(ListView):
    """Manage residents - syndic and superadmin only"""
    model = User
    template_name = 'finance/resident_management.html'
    context_object_name = 'residents'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return User.objects.filter(role='RESIDENT').select_related('created_by').prefetch_related('status').order_by('username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Ajouter un Résident',
                'url': reverse_lazy('finance:resident_create'),
                'icon': 'fas fa-plus',
                'type': 'primary'
            }
        ]
        
        # Statistiques des résidents
        from django.utils import timezone
        from datetime import timedelta
        
        # Total des résidents
        context['total_residents'] = User.objects.filter(role='RESIDENT').count()
        
        # Résidents avec appartement
        context['residents_with_apartment'] = User.objects.filter(
            role='RESIDENT', 
            apartment__isnull=False
        ).exclude(apartment='').count()
        
        # Nouveaux résidents (30 derniers jours)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        context['recent_residents'] = User.objects.filter(
            role='RESIDENT',
            date_joined__gte=thirty_days_ago
        ).count()
        
        # Résidents actifs
        context['active_residents'] = User.objects.filter(
            role='RESIDENT',
            is_active=True
        ).count()
        
        return context


class ResidentCreateView(CreateView):
    """Create resident - syndic and superadmin only"""
    model = User
    template_name = 'finance/resident_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'apartment', 'address']
    success_url = reverse_lazy('finance:resident_management')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        try:
            user = form.save(commit=False)
            user.role = 'RESIDENT'
            user.is_active = True
            user.created_by = self.request.user  # Track who created this resident
            user.set_password('resident123')  # Default password
            
            # Validate uniqueness before saving
            user.clean()
            user.save()
            
            # Create resident status
            ResidentStatus.objects.create(resident=user)
            
            messages.success(self.request, f"Résident {user.username} créé avec succès. Mot de passe: resident123")
            return super().form_valid(form)
            
        except ValidationError as e:
            # Handle validation errors (like duplicate apartment)
            for field, errors in e.message_dict.items():
                for error in errors:
                    form.add_error(field, error)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error('apartment', "Un résident existe déjà pour cet appartement.")
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Retour à la liste',
                'url': reverse_lazy('finance:resident_management'),
                'icon': 'fas fa-arrow-left',
                'type': 'outline'
            }
        ]
        
        # Get existing apartments to show in help text
        existing_apartments = User.objects.filter(
            role='RESIDENT', 
            apartment__isnull=False
        ).exclude(apartment='').values_list('apartment', flat=True)
        
        context['existing_apartments'] = list(existing_apartments)
        context['creator'] = self.request.user
        
        return context


class ResidentUpdateView(UpdateView):
    """Update resident - syndic and superadmin only"""
    model = User
    template_name = 'finance/resident_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'apartment', 'address', 'is_active']
    success_url = reverse_lazy('finance:resident_management')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return User.objects.filter(role='RESIDENT')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Retour à la liste',
                'url': reverse_lazy('finance:resident_management'),
                'icon': 'fas fa-arrow-left',
                'type': 'outline'
            }
        ]
        
        context['creator'] = self.request.user
        
        return context


class SyndicManagementView(ListView):
    """Manage syndics - superadmin only"""
    model = User
    template_name = 'finance/syndic_management.html'
    context_object_name = 'syndics'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'SUPERADMIN':
            messages.error(request, "Accès non autorisé. Seuls les super administrateurs peuvent gérer les syndics.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return User.objects.filter(role='SYNDIC').order_by('username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_syndics'] = User.objects.filter(role='SYNDIC').count()
        context['active_syndics'] = User.objects.filter(role='SYNDIC', is_active=True).count()
        return context


class SyndicCreateView(CreateView):
    """Create syndic - superadmin only"""
    model = User
    template_name = 'finance/syndic_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'address']
    success_url = reverse_lazy('finance:syndic_management')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'SUPERADMIN':
            messages.error(request, "Accès non autorisé. Seuls les super administrateurs peuvent créer des syndics.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        user = form.save(commit=False)
        user.role = 'SYNDIC'
        user.is_active = True
        user.set_password('syndic123')  # Default password
        user.save()
        
        messages.success(self.request, f"Syndic {user.username} créé avec succès. Mot de passe: syndic123")
        return super().form_valid(form)


class SyndicUpdateView(UpdateView):
    """Update syndic - superadmin only"""
    model = User
    template_name = 'finance/syndic_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'address', 'is_active']
    success_url = reverse_lazy('finance:syndic_management')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'SUPERADMIN':
            messages.error(request, "Accès non autorisé. Seuls les super administrateurs peuvent modifier les syndics.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return User.objects.filter(role='SYNDIC')


class SyndicDetailView(DetailView):
    """View syndic details - superadmin only"""
    model = User
    template_name = 'finance/syndic_detail.html'
    context_object_name = 'syndic'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'SUPERADMIN':
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return User.objects.filter(role='SYNDIC')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        syndic = self.get_object()
        
        # Get syndic's activity statistics
        context['documents_created'] = Document.objects.filter(uploaded_by=syndic).count()
        context['notifications_sent'] = Notification.objects.filter(sender=syndic).count()
        context['residents_managed'] = User.objects.filter(role='RESIDENT').count()
        
        # Recent activity
        context['recent_documents'] = Document.objects.filter(uploaded_by=syndic).order_by('-created_at')[:5]
        context['recent_notifications'] = Notification.objects.filter(sender=syndic).order_by('-created_at')[:5]
        
        return context


class ResidentDetailView(DetailView):
    """Resident detail - syndic and superadmin only"""
    model = User
    template_name = 'finance/resident_detail.html'
    context_object_name = 'resident'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return User.objects.filter(role='RESIDENT')



class CalendarListView(TemplateView):
    template_name = 'finance/calendar_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role in ['SYNDIC', 'SUPERADMIN']:
            events = Event.objects.all().prefetch_related('participants')
        else:
            # resident sees events targeting all residents or specifically included
            events = Event.objects.filter(Q(audience='ALL_RESIDENTS') | Q(participants=self.request.user)).distinct()
        context['events'] = events.order_by('start_at')
        
        # Actions de page pour l'en-tête
        if self.request.user.role in ['SUPERADMIN', 'SYNDIC']:
            context['page_actions'] = [
                {
                    'label': 'Nouvel Événement',
                    'url': reverse_lazy('finance:event_create'),
                    'icon': 'fas fa-plus',
                    'type': 'success'
                }
            ]
        
        return context


class EventCreateView(CreateView):
    model = Event
    template_name = 'finance/event_form.html'
    fields = ['title','description','event_type','start_at','end_at','audience','participants','reminder_minutes_before']
    success_url = reverse_lazy('finance:calendar')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SYNDIC', 'SUPERADMIN']:
            messages.error(request, 'Accès non autorisé.')
            return redirect('finance:calendar')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Retour au Calendrier',
                'url': reverse_lazy('finance:calendar'),
                'icon': 'fas fa-arrow-left',
                'type': 'outline'
            }
        ]
        
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Événement créé avec succès.')
        return super().form_valid(form)


class ResidentReportListView(ListView):
    """List reports. Residents see their own; syndic/superadmin see all."""
    model = ResidentReport
    template_name = 'finance/report_list.html'
    context_object_name = 'reports'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = ResidentReport.objects.all()
        
        if self.request.user.role == 'RESIDENT':
            return queryset.filter(resident=self.request.user)
        return queryset.select_related('resident', 'reviewed_by')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistiques pour les syndics
        if self.request.user.role in ['SYNDIC', 'SUPERADMIN']:
            context['total_reports'] = ResidentReport.objects.count()
            context['new_reports'] = ResidentReport.objects.filter(status='NEW').count()
            context['in_progress_reports'] = ResidentReport.objects.filter(status='IN_PROGRESS').count()
            context['resolved_reports'] = ResidentReport.objects.filter(status='RESOLVED').count()
        
        return context


class ResidentReportCreateView(CreateView):
    """Create a new resident report (resident only)."""
    model = ResidentReport
    template_name = 'finance/report_form.html'
    fields = ['title', 'description', 'category', 'photo', 'location']
    success_url = reverse_lazy('finance:report_list')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'RESIDENT':
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.resident = self.request.user
        messages.success(self.request, "Votre rapport a été enregistré avec succès.")
        return super().form_valid(form)


class ReportManagementView(ListView):
    """List all reports for syndics and superadmins management."""
    model = ResidentReport
    template_name = 'finance/report_management.html'
    context_object_name = 'reports'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SYNDIC', 'SUPERADMIN']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ResidentReport.objects.all().select_related('resident', 'reviewed_by')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistiques des rapports
        context['total_reports'] = ResidentReport.objects.count()
        context['new_reports'] = ResidentReport.objects.filter(status='NEW').count()
        context['in_progress_reports'] = ResidentReport.objects.filter(status='IN_PROGRESS').count()
        context['resolved_reports'] = ResidentReport.objects.filter(status='RESOLVED').count()
        context['recent_reports'] = ResidentReport.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()
        
        return context


class ReportUpdateView(UpdateView):
    """Update report status and add comments (syndic/superadmin only)."""
    model = ResidentReport
    template_name = 'finance/report_update.html'
    fields = ['status']
    success_url = reverse_lazy('finance:report_management')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SYNDIC', 'SUPERADMIN']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.reviewed_by = self.request.user
        form.instance.reviewed_at = timezone.now()
        messages.success(self.request, f"Statut du rapport mis à jour : {form.instance.get_status_display()}")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.comments.filter(is_internal=False).order_by('created_at')
        return context


class ReportCommentCreateView(CreateView):
    """Add comment to a report."""
    model = ReportComment
    template_name = 'finance/report_comment_form.html'
    fields = ['comment', 'is_internal']
    success_url = reverse_lazy('finance:report_management')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.report = get_object_or_404(ResidentReport, pk=self.kwargs['report_id'])
        form.instance.author = self.request.user
        
        # Seuls les syndics peuvent ajouter des commentaires internes
        if form.instance.is_internal and self.request.user.role not in ['SYNDIC', 'SUPERADMIN']:
            form.instance.is_internal = False
        
        messages.success(self.request, "Commentaire ajouté avec succès.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Expose report_id and report to the template for links
        report_id = self.kwargs.get('report_id')
        context['report_id'] = report_id
        if report_id:
            context['report'] = get_object_or_404(ResidentReport, pk=report_id)
        return context

    def get_success_url(self):
        return reverse_lazy('finance:report_detail', kwargs={'pk': self.kwargs['report_id']})


class ResidentReportDetailView(DetailView):
    """Show details of a resident report. Residents can view only their own."""
    model = ResidentReport
    template_name = 'finance/report_detail.html'
    context_object_name = 'report'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = ResidentReport.objects.select_related('resident', 'reviewed_by')
        if self.request.user.role == 'RESIDENT':
            return qs.filter(resident=self.request.user)
        return qs


class DocumentListView(ListView):
    """List documents - filtered by role"""
    model = Document
    template_name = 'finance/document_list.html'
    context_object_name = 'documents'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Document.objects.select_related('resident', 'uploaded_by').order_by('-date')
        
        # Filtres pour les syndics
        if self.request.user.role in ['SUPERADMIN', 'SYNDIC']:
            # Filtre par type de document
            document_type = self.request.GET.get('document_type')
            if document_type:
                qs = qs.filter(document_type=document_type)
            
            # Filtre par statut de paiement
            payment_status = self.request.GET.get('payment_status')
            if payment_status == 'paid':
                qs = qs.filter(is_paid=True)
            elif payment_status == 'unpaid':
                qs = qs.filter(is_paid=False)
            elif payment_status == 'overdue':
                from django.utils import timezone
                thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
                qs = qs.filter(is_paid=False, date__lt=thirty_days_ago)
            
            # Filtre par dates
            date_start = self.request.GET.get('date_start')
            if date_start:
                qs = qs.filter(date__gte=date_start)
            
            date_end = self.request.GET.get('date_end')
            if date_end:
                qs = qs.filter(date__lte=date_end)
        
        # Filtre archives
        show_archived = self.request.GET.get('archived') == '1'
        if not show_archived:
            qs = qs.filter(is_archived=False)
            
        # Filtre pour les résidents
        if self.request.user.role == 'RESIDENT':
            qs = qs.filter(resident=self.request.user)
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_resident_view'] = (self.request.user.role == 'RESIDENT')
        
        # Statistiques pour les syndics
        if self.request.user.role in ['SUPERADMIN', 'SYNDIC']:
            all_docs = Document.objects.filter(is_archived=False)
            context['stats'] = {
                'total': all_docs.count(),
                'paid': all_docs.filter(is_paid=True).count(),
                'unpaid': all_docs.filter(is_paid=False).count(),
                'overdue': sum(1 for doc in all_docs if doc.is_overdue),
                'total_amount': all_docs.aggregate(total=Sum('amount'))['total'] or 0,
                'paid_amount': all_docs.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0,
            }
        
        return context


class DocumentCreateView(CreateView):
    """Create document - syndic and superadmin only"""
    model = Document
    template_name = 'finance/document_form.html'
    fields = ['title', 'file', 'amount', 'date', 'document_type', 'resident', 'description']
    success_url = reverse_lazy('finance:document_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['residents'] = User.objects.filter(role='RESIDENT')
        return context
    
    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        messages.success(self.request, "Document créé avec succès.")
        return super().form_valid(form)


class DocumentDetailView(DetailView):
    """View document details"""
    model = Document
    template_name = 'finance/document_detail.html'
    context_object_name = 'document'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        
        document = self.get_object()
        # Only the document owner or syndic/admin can view
        if document.resident != request.user and request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        
        return super().dispatch(request, *args, **kwargs)


class NotificationListView(ListView):
    """List notifications - filtered by role"""
    model = Notification
    template_name = 'finance/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Notification.objects.none()
        if self.request.user.role == 'RESIDENT':
            return Notification.objects.filter(recipients=self.request.user, is_active=True).order_by('-created_at')
        return Notification.objects.filter(is_active=True).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_resident_view'] = (self.request.user.is_authenticated and self.request.user.role == 'RESIDENT')
        return context


class NotificationCreateView(CreateView):
    """Create notification - syndic and superadmin only"""
    model = Notification
    template_name = 'finance/notification_form.html'
    fields = ['title', 'message', 'notification_type', 'priority', 'recipients']
    success_url = reverse_lazy('finance:notification_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Retour aux Notifications',
                'url': reverse_lazy('finance:notification_list'),
                'icon': 'fas fa-arrow-left',
                'type': 'outline'
            }
        ]
        
        # Liste des résidents pour la sélection
        context['residents'] = User.objects.filter(role='RESIDENT').order_by('first_name', 'last_name')
        
        return context
    
    def get_initial(self):
        initial = super().get_initial()
        # Préremplir le destinataire si resident_id est passé en querystring
        resident_id = self.request.GET.get('resident_id')
        # Ou si un email de résident est passé
        resident_email = self.request.GET.get('email') or self.request.GET.get('resident_email')
        if resident_id:
            try:
                resident = User.objects.get(pk=resident_id, role='RESIDENT')
                # Pour un champ ManyToMany, l'initial accepte une liste de pks
                initial['recipients'] = [resident.pk]
            except User.DoesNotExist:
                pass
        elif resident_email:
            try:
                resident = User.objects.get(email=resident_email, role='RESIDENT')
                initial['recipients'] = [resident.pk]
            except User.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        form.instance.sender = self.request.user
        response = super().form_valid(form)

        # S'assurer que le résident pré-sélectionné est bien ajouté (au cas où le formulaire ne l'a pas gardé)
        resident_id = self.request.GET.get('resident_id') or self.request.POST.get('resident_id')
        resident_email = (
            self.request.GET.get('email') or self.request.GET.get('resident_email') or
            self.request.POST.get('email') or self.request.POST.get('resident_email')
        )
        if resident_id:
            try:
                resident = User.objects.get(pk=resident_id, role='RESIDENT')
                # Si un résident précis est ciblé, on force la liste des destinataires à ce seul résident
                self.object.recipients.set([resident])
            except User.DoesNotExist:
                pass
        elif resident_email:
            try:
                resident = User.objects.get(email=resident_email, role='RESIDENT')
                self.object.recipients.set([resident])
            except User.DoesNotExist:
                pass

        # Envoyer un email HTML aux destinataires (si SMTP configuré)
        try:
            from .emails import send_templated_email
            subject = self.object.title or "Notification"
            for user in self.object.recipients.all():
                if not getattr(user, 'email', None):
                    continue
                # Construire le contexte dynamiquement (avec compatibilité si certains champs n'existent pas)
                notification_type = getattr(self.object, 'get_notification_type_display', None)
                notification_type = notification_type() if callable(notification_type) else getattr(self.object, 'notification_type', None)
                priority = getattr(self.object, 'get_priority_display', None)
                priority = priority() if callable(priority) else getattr(self.object, 'priority', None)
                amount = getattr(self.object, 'amount', None)
                date_obj = getattr(self.object, 'date', None)
                date_str = date_obj.strftime('%d/%m/%Y') if hasattr(date_obj, 'strftime') else (date_obj or None)
                link = getattr(self.object, 'link', None)

                context = {
                    'subject': subject,
                    'resident_name': (user.get_full_name() or user.username),
                    'notification_type': notification_type,
                    'priority': priority,
                    'amount': amount,
                    'date': date_str,
                    'message': (self.object.message or ''),
                    'intro_text': "Vous avez reçu une nouvelle notification.",
                    'link': link,
                }
                send_templated_email(
                    subject=subject,
                    to_email=user.email,
                    template_name='emails/notification_generic.html',
                    context=context,
                )
        except Exception:
            # Ne pas bloquer l'application si l'email échoue
            pass

        messages.success(self.request, "Notification créée avec succès.")
        return response


class NotificationDetailView(DetailView):
    """View a single notification"""
    model = Notification
    template_name = 'finance/notification_detail.html'
    context_object_name = 'notification'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        notification = self.get_object()
        # Residents can only view notifications that include them
        if request.user.role == 'RESIDENT' and request.user not in notification.recipients.all():
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:notification_list')
        return super().dispatch(request, *args, **kwargs)

class PaymentCreateView(CreateView):
    """Create payment for a document - residents only"""
    model = Payment
    template_name = 'finance/payment_form.html'
    fields = ['amount', 'payment_method', 'payment_date', 'reference', 'notes', 'payment_proof']
    success_url = reverse_lazy('finance:document_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role != 'RESIDENT':
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document_id = self.kwargs.get('document_id')
        context['document'] = get_object_or_404(Document, id=document_id, resident=self.request.user)
        return context
    
    def form_valid(self, form):
        document_id = self.kwargs.get('document_id')
        document = get_object_or_404(Document, id=document_id, resident=self.request.user)
        form.instance.document = document
        messages.success(self.request, "Paiement enregistré avec succès. Il sera vérifié par le syndic.")
        return super().form_valid(form)


class CustomLoginView(TemplateView):
    """Custom login view"""
    template_name = 'finance/login.html'
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('finance:home')
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenue, {user.username} !")
                return redirect('finance:home')
            else:
                messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
        else:
            messages.error(request, "Veuillez remplir tous les champs.")
        
        return self.get(request, *args, **kwargs)


class CustomLogoutView(TemplateView):
    """Custom logout view"""
    template_name = 'finance/logout.html'
    
    def get(self, request, *args, **kwargs):
        logout(request)
        messages.success(request, "Vous avez été déconnecté avec succès.")
        return super().get(request, *args, **kwargs)


@method_decorator(csrf_exempt, name='dispatch')
class SendNotificationAPI(View):
    """API endpoint for sending notifications via SMS/Email"""
    
    def post(self, request):
        if not request.user.is_authenticated or request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        try:
            data = json.loads(request.body)
            notification_id = data.get('notification_id')
            send_sms_enabled = data.get('send_sms', False)
            send_email_enabled = data.get('send_email', False)
            
            notification = get_object_or_404(Notification, id=notification_id)
            
            results = {
                'sms_sent': 0,
                'email_sent': 0,
                'errors': []
            }
            
            for recipient in notification.recipients.all():
                try:
                    if send_sms_enabled and recipient.phone:
                        send_sms(recipient.phone, f"{notification.title}\n\n{notification.message}")
                        results['sms_sent'] += 1
                    
                    if send_email_enabled and recipient.email:
                        send_email(recipient.email, notification.title, notification.message)
                        results['email_sent'] += 1
                        
                except Exception as e:
                    results['errors'].append(f"Erreur pour {recipient.username}: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'message': f"Notifications envoyées: {results['sms_sent']} SMS, {results['email_sent']} emails",
                'results': results
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ==================== VUES POUR LA GESTION DES DÉPENSES ====================

class DepenseListView(ListView):
    """Liste des dépenses - accès différencié selon le rôle"""
    model = Depense
    template_name = 'finance/depense_list.html'
    context_object_name = 'depenses'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Depense.objects.all()
        
        # Filtres
        categorie = self.request.GET.get('categorie')
        if categorie:
            queryset = queryset.filter(categorie=categorie)
        
        date_debut = self.request.GET.get('date_debut')
        if date_debut:
            queryset = queryset.filter(date_depense__gte=date_debut)
        
        date_fin = self.request.GET.get('date_fin')
        if date_fin:
            queryset = queryset.filter(date_depense__lte=date_fin)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        
        context['categories'] = Depense.CATEGORIES
        context['total_depenses'] = queryset.aggregate(total=Sum('montant'))['total'] or 0
        context['can_manage'] = self.request.user.role in ['SUPERADMIN', 'SYNDIC']
        
        # Calcul de la dépense moyenne
        depense_count = queryset.count()
        if depense_count > 0 and context['total_depenses'] > 0:
            context['depense_moyenne'] = context['total_depenses'] / depense_count
        else:
            context['depense_moyenne'] = 0
        
        # Actions de page pour l'en-tête
        if context['can_manage']:
            context['page_actions'] = [
                {
                    'label': 'Nouvelle Dépense',
                    'url': reverse_lazy('finance:depense_create'),
                    'icon': 'fas fa-plus',
                    'type': 'success'
                }
            ]
        
        # Données pour les graphiques
        if self.request.user.role == 'RESIDENT':
            chart_data = self.get_chart_data()
            context['chart_data'] = chart_data
            # Sérialiser en JSON pour JavaScript
            import json
            context['chart_data_json'] = json.dumps(chart_data)
        
        return context
    
    def get_chart_data(self):
        """Données pour les graphiques des résidents"""
        # Répartition par catégorie
        categories_data = (
            Depense.objects
            .values('categorie')
            .annotate(total=Sum('montant'))
            .order_by('-total')
        )
        
        # Évolution mensuelle (6 derniers mois)
        from django.utils.dateparse import parse_date
        from datetime import datetime, timedelta
        import calendar
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=180)  # 6 mois
        
        monthly_data = {}
        current_date = start_date
        while current_date <= end_date:
            month_key = f"{current_date.year}-{current_date.month:02d}"
            month_name = f"{calendar.month_name[current_date.month][:3]} {current_date.year}"
            monthly_data[month_name] = 0
            current_date = current_date.replace(day=1)
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        monthly_expenses = (
            Depense.objects
            .filter(date_depense__gte=start_date, date_depense__lte=end_date)
            .extra({'month': "strftime('%%Y-%%m', date_depense)"})
            .values('month')
            .annotate(total=Sum('montant'))
        )
        
        for expense in monthly_expenses:
            year, month = expense['month'].split('-')
            month_name = f"{calendar.month_name[int(month)][:3]} {year}"
            if month_name in monthly_data:
                monthly_data[month_name] = float(expense['total'])
        
        return {
            'categories': [
                {
                    'categorie': dict(Depense.CATEGORIES).get(item['categorie'], item['categorie']),
                    'montant': float(item['total'])
                }
                for item in categories_data
            ],
            'monthly': [
                {'month': month, 'total': total}
                for month, total in monthly_data.items()
            ]
        }


class DepenseCreateView(CreateView):
    """Créer une nouvelle dépense - syndics seulement"""
    model = Depense
    template_name = 'finance/depense_form.html'
    fields = ['titre', 'description', 'montant', 'categorie', 'date_depense']
    success_url = reverse_lazy('finance:depense_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:depense_list')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.ajoute_par = self.request.user
        messages.success(self.request, "Dépense ajoutée avec succès.")
        return super().form_valid(form)


class DepenseUpdateView(UpdateView):
    """Modifier une dépense - syndics seulement"""
    model = Depense
    template_name = 'finance/depense_form.html'
    fields = ['titre', 'description', 'montant', 'categorie', 'date_depense']
    success_url = reverse_lazy('finance:depense_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:depense_list')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, "Dépense modifiée avec succès.")
        return super().form_valid(form)


class DepenseDetailView(DetailView):
    """Détails d'une dépense"""
    model = Depense
    template_name = 'finance/depense_detail.html'
    context_object_name = 'depense'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)


class DepenseDeleteView(View):
    """Supprimer une dépense - syndics seulement"""
    
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:depense_list')
        
        depense = get_object_or_404(Depense, pk=pk)
        depense.delete()
        messages.success(request, "Dépense supprimée avec succès.")
        return redirect('finance:depense_list')


# ==================== SYSTÈME DE DÉTECTION DES IMPAYÉS ====================

class OverduePaymentsDashboardView(TemplateView):
    """Tableau de bord des impayés - syndics seulement"""
    template_name = 'finance/overdue_dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Documents impayés par catégorie
        from django.utils import timezone
        today = timezone.now().date()
        
        unpaid_docs = Document.objects.filter(is_paid=False, is_archived=False).select_related('resident')
        
        # Catégoriser les impayés
        due_soon = []      # Échéance dans 7 jours
        overdue_30 = []    # 30-59 jours de retard
        overdue_60 = []    # 60-89 jours de retard
        critical_90 = []   # 90+ jours de retard
        
        total_overdue_amount = Decimal('0')
        
        for doc in unpaid_docs:
            days_until_due = (doc.due_date - today).days
            days_overdue = doc.days_overdue
            
            if 0 <= days_until_due <= 7:
                due_soon.append(doc)
            elif 30 <= days_overdue < 60:
                overdue_30.append(doc)
                total_overdue_amount += doc.amount
            elif 60 <= days_overdue < 90:
                overdue_60.append(doc)
                total_overdue_amount += doc.amount
            elif days_overdue >= 90:
                critical_90.append(doc)
                total_overdue_amount += doc.amount
        
        # Statistiques des notifications envoyées
        from .models import OverdueNotificationLog
        recent_notifications = OverdueNotificationLog.objects.filter(
            created_at__gte=today - timezone.timedelta(days=30)
        ).select_related('document__resident')
        
        context.update({
            'due_soon': due_soon,
            'overdue_30': overdue_30,
            'overdue_60': overdue_60,
            'critical_90': critical_90,
            'total_overdue_amount': total_overdue_amount,
            'recent_notifications': recent_notifications[:10],
            'stats': {
                'due_soon_count': len(due_soon),
                'overdue_30_count': len(overdue_30),
                'overdue_60_count': len(overdue_60),
                'critical_90_count': len(critical_90),
                'total_notifications': recent_notifications.count(),
            }
        })
        
        return context


class RunOverdueDetectionView(View):
    """Exécuter manuellement la détection des impayés"""
    
    def post(self, request):
        if not request.user.is_authenticated or request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        try:
            # Importer et exécuter la commande
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('detect_overdue_payments', stdout=output)
            
            messages.success(request, "Détection des impayés exécutée avec succès.")
            return JsonResponse({
                'success': True,
                'message': 'Détection terminée',
                'output': output.getvalue()
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ===== VUE DE TEST POUR LES COMPOSANTS =====
class TestComponentsView(TemplateView):
    """Vue de test pour vérifier le fonctionnement des composants"""
    template_name = 'test_components.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Actions pour les cartes
        context['card_actions'] = [
            {
                'label': 'Voir Détails',
                'url': '#',
                'icon': 'fas fa-eye',
                'type': 'primary'
            },
            {
                'label': 'Modifier',
                'url': '#',
                'icon': 'fas fa-edit',
                'type': 'warning'
            }
        ]
        
        # Actions pour l'en-tête
        context['header_actions'] = [
            {
                'label': 'Nouveau',
                'url': '#',
                'icon': 'fas fa-plus',
                'type': 'success'
            },
            {
                'label': 'Exporter',
                'url': '#',
                'icon': 'fas fa-download',
                'type': 'info'
            }
        ]
        
        # En-têtes de tableau
        context['table_headers'] = [
            {'label': 'Nom', 'icon': 'fas fa-user', 'sortable': True},
            {'label': 'Email', 'icon': 'fas fa-envelope', 'sortable': True},
            {'label': 'Statut', 'icon': 'fas fa-check-circle', 'sortable': False},
            {'label': 'Actions', 'icon': 'fas fa-cog', 'sortable': False}
        ]
        
        # Données de tableau
        context['table_rows'] = [
            {
                'cells': [
                    {'value': 'Jean Dupont'},
                    {'value': 'jean@example.com'},
                    {'type': 'badge', 'value': 'Actif', 'color': 'success'},
                    {
                        'type': 'actions',
                        'actions': [
                            {'url': '#', 'icon': 'fas fa-eye', 'title': 'Voir'},
                            {'url': '#', 'icon': 'fas fa-edit', 'title': 'Modifier'}
                        ]
                    }
                ]
            },
            {
                'cells': [
                    {'value': 'Marie Martin'},
                    {'value': 'marie@example.com'},
                    {'type': 'badge', 'value': 'Inactif', 'color': 'warning'},
                    {
                        'type': 'actions',
                        'actions': [
                            {'url': '#', 'icon': 'fas fa-eye', 'title': 'Voir'},
                            {'url': '#', 'icon': 'fas fa-edit', 'title': 'Modifier'}
                        ]
                    }
                ]
            }
        ]
        
        return context


class UserProfileView(TemplateView):
    """User profile page - authenticated users only"""
    template_name = 'finance/user_profile.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Veuillez vous connecter pour accéder à votre profil.")
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Actions de page pour l'en-tête
        context['page_actions'] = [
            {
                'label': 'Retour au tableau de bord',
                'url': reverse_lazy('finance:home'),
                'icon': 'fas fa-arrow-left',
                'type': 'outline'
            }
        ]
        
        # Informations de l'utilisateur
        context['user_info'] = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': getattr(user, 'phone', ''),
            'apartment': getattr(user, 'apartment', ''),
            'address': getattr(user, 'address', ''),
            'role': user.role,
            'is_active': user.is_active,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        }
        
        # Statistiques selon le rôle
        if user.role in ['SYNDIC', 'SUPERADMIN']:
            context['stats'] = {
                'total_residents': User.objects.filter(role='RESIDENT').count(),
                'total_documents': Document.objects.count(),
                'total_expenses': Depense.objects.count(),
                'unread_notifications': Notification.objects.filter(
                    recipients=user, 
                    is_read=False
                ).count(),
            }
        elif user.role == 'RESIDENT':
            context['stats'] = {
                'my_documents': Document.objects.filter(resident=user).count(),
                'my_payments': Payment.objects.filter(document__resident=user).count(),
                'my_notifications': Notification.objects.filter(
                    recipients=user
                ).count(),
                'unread_notifications': Notification.objects.filter(
                    recipients=user, 
                    is_read=False
                ).count(),
            }
        
        return context