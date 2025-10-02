from django.urls import path
from . import views
from . import chatbot_views
from . import api_views

app_name = 'finance'

urlpatterns = [
    # Home and authentication
    path('', views.HomeView.as_view(), name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('profile/', views.UserProfileView.as_view(), name='user_profile'),
    
    # Test components (development only)
    path('test-components/', views.TestComponentsView.as_view(), name='test_components'),
    
    # Dashboards
    path('syndic-dashboard/', views.SyndicDashboardView.as_view(), name='syndic_dashboard'),
    path('resident-dashboard/', views.ResidentDashboardView.as_view(), name='resident_dashboard'),
    
    # Resident management (syndic only)
    path('residents/', views.ResidentManagementView.as_view(), name='resident_management'),
    path('residents/create/', views.ResidentCreateView.as_view(), name='resident_create'),
    path('residents/<int:pk>/', views.ResidentDetailView.as_view(), name='resident_detail'),
    path('residents/<int:pk>/edit/', views.ResidentUpdateView.as_view(), name='resident_update'),
    
    # Syndic management (superadmin only)
    path('syndics/', views.SyndicManagementView.as_view(), name='syndic_management'),
    path('syndics/create/', views.SyndicCreateView.as_view(), name='syndic_create'),
    path('syndics/<int:pk>/', views.SyndicDetailView.as_view(), name='syndic_detail'),
    path('syndics/<int:pk>/edit/', views.SyndicUpdateView.as_view(), name='syndic_update'),
    
    # Document management
    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('documents/create/', views.DocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    
    # Payment management
    path('payments/create/<int:document_id>/', views.PaymentCreateView.as_view(), name='payment_create'),
    
    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notification_list'),
    path('notifications/create/', views.NotificationCreateView.as_view(), name='notification_create'),
    path('notifications/<int:pk>/', views.NotificationDetailView.as_view(), name='notification_detail'),
    
    # Resident reports
    path('reports/', views.ResidentReportListView.as_view(), name='report_list'),
    path('reports/create/', views.ResidentReportCreateView.as_view(), name='report_create'),
    path('reports/<int:pk>/', views.ResidentReportDetailView.as_view(), name='report_detail'),
    path('reports/management/', views.ReportManagementView.as_view(), name='report_management'),
    path('reports/<int:pk>/update/', views.ReportUpdateView.as_view(), name='report_update'),
    path('reports/<int:report_id>/comment/', views.ReportCommentCreateView.as_view(), name='report_comment'),
    
    

    # Calendar
    path('calendar/', views.CalendarListView.as_view(), name='calendar'),
    path('calendar/create/', views.EventCreateView.as_view(), name='event_create'),
    
    # Expense management
    path('depenses/', views.DepenseListView.as_view(), name='depense_list'),
    path('depenses/create/', views.DepenseCreateView.as_view(), name='depense_create'),
    path('depenses/<int:pk>/', views.DepenseDetailView.as_view(), name='depense_detail'),
    path('depenses/<int:pk>/edit/', views.DepenseUpdateView.as_view(), name='depense_update'),
    path('depenses/<int:pk>/delete/', views.DepenseDeleteView.as_view(), name='depense_delete'),
    
    # Overdue payments management
    path('impayes/', views.OverduePaymentsDashboardView.as_view(), name='overdue_dashboard'),
    path('api/run-overdue-detection/', views.RunOverdueDetectionView.as_view(), name='run_overdue_detection'),
    
    # Chatbot / Assistant virtuel
    path('assistant/', chatbot_views.ChatbotView.as_view(), name='chatbot'),
    path('api/chatbot/message/', chatbot_views.ChatbotMessageAPI.as_view(), name='chatbot_message_api'),
    path('assistant/faq/', chatbot_views.ChatbotFAQManagementView.as_view(), name='chatbot_faq_management'),
    path('assistant/faq/create/', chatbot_views.ChatbotFAQCreateView.as_view(), name='chatbot_faq_create'),
    
    # API endpoints
    path('api/navigation-stats/', api_views.NavigationStatsAPI.as_view(), name='navigation_stats_api'),
    path('api/send-notification/', views.SendNotificationAPI.as_view(), name='send_notification_api'),
]