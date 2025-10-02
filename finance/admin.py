from django.contrib import admin
from .models import Document, Notification, Payment, ResidentStatus, Depense, OverdueNotificationLog, ChatbotFAQ, ChatbotConversation, ChatbotMessage


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'resident', 'amount', 'document_type', 'date', 'is_paid', 'uploaded_by']
    list_filter = ['document_type', 'is_paid', 'date', 'created_at']
    search_fields = ['title', 'resident__username', 'resident__first_name', 'resident__last_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resident', 'uploaded_by')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'priority', 'sender', 'is_read', 'created_at']
    list_filter = ['notification_type', 'priority', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'sender__username']
    readonly_fields = ['created_at', 'read_at']
    filter_horizontal = ['recipients']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sender').prefetch_related('recipients')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['document', 'amount', 'payment_method', 'payment_date', 'is_verified', 'verified_by']
    list_filter = ['payment_method', 'is_verified', 'payment_date']
    search_fields = ['document__title', 'document__resident__username', 'reference']
    readonly_fields = ['created_at', 'verified_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('document__resident', 'verified_by')


@admin.register(ResidentStatus)
class ResidentStatusAdmin(admin.ModelAdmin):
    list_display = ['resident', 'total_due', 'total_paid', 'balance', 'status_category', 'last_updated']
    list_filter = ['last_updated']
    search_fields = ['resident__username', 'resident__first_name', 'resident__last_name']
    readonly_fields = ['last_updated']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resident')
    
    def balance(self, obj):
        return obj.balance
    balance.short_description = 'Solde'
    balance.admin_order_field = 'total_due'


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ['titre', 'categorie', 'montant', 'date_depense', 'ajoute_par', 'is_grosse_depense', 'created_at']
    list_filter = ['categorie', 'date_depense', 'created_at', 'ajoute_par']
    search_fields = ['titre', 'description', 'ajoute_par__username', 'ajoute_par__first_name', 'ajoute_par__last_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date_depense', '-created_at']
    date_hierarchy = 'date_depense'
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('titre', 'description', 'montant', 'categorie', 'date_depense')
        }),
        ('Gestion', {
            'fields': ('ajoute_par',)
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ajoute_par')
    
    def is_grosse_depense(self, obj):
        return obj.is_grosse_depense
    is_grosse_depense.boolean = True
    is_grosse_depense.short_description = 'Grosse dépense'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si c'est une nouvelle dépense
            obj.ajoute_par = request.user
        super().save_model(request, obj, form, change)


@admin.register(OverdueNotificationLog)
class OverdueNotificationLogAdmin(admin.ModelAdmin):
    list_display = ['document', 'notification_type', 'sent_to_resident', 'sent_to_syndic', 'created_at']
    list_filter = ['notification_type', 'sent_to_resident', 'sent_to_syndic', 'created_at']
    search_fields = ['document__title', 'document__resident__username', 'document__resident__first_name', 'document__resident__last_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('document__resident')


@admin.register(ChatbotFAQ)
class ChatbotFAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'category', 'usage_count', 'is_active', 'created_by', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['question', 'keywords', 'answer']
    readonly_fields = ['usage_count', 'created_at', 'updated_at']
    ordering = ['-usage_count', '-created_at']
    
    fieldsets = (
        ('Question et Réponse', {
            'fields': ('question', 'keywords', 'answer', 'category')
        }),
        ('Configuration', {
            'fields': ('is_active', 'created_by')
        }),
        ('Statistiques', {
            'fields': ('usage_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


@admin.register(ChatbotConversation)
class ChatbotConversationAdmin(admin.ModelAdmin):
    list_display = ['user', 'session_id', 'started_at', 'last_activity', 'is_active']
    list_filter = ['is_active', 'started_at', 'last_activity']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'session_id']
    readonly_fields = ['session_id', 'started_at', 'last_activity']
    ordering = ['-last_activity']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(ChatbotMessage)
class ChatbotMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'content_preview', 'faq_used', 'is_helpful', 'created_at']
    list_filter = ['message_type', 'is_helpful', 'created_at']
    search_fields = ['content', 'conversation__user__username']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Contenu'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('conversation__user', 'faq_used')