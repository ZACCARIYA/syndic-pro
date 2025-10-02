from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, TemplateView, View
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
import json
import uuid

from .models import ChatbotFAQ, ChatbotConversation, ChatbotMessage, Notification

User = get_user_model()


class ChatbotView(TemplateView):
    """Interface principale du chatbot"""
    template_name = 'finance/chatbot.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Récupérer ou créer une conversation active
        session_id = self.request.session.get('chatbot_session')
        if not session_id:
            session_id = str(uuid.uuid4())
            self.request.session['chatbot_session'] = session_id
        
        conversation, created = ChatbotConversation.objects.get_or_create(
            user=self.request.user,
            session_id=session_id,
            defaults={'is_active': True}
        )
        
        # Messages de la conversation
        messages = conversation.messages.all()
        
        # Categories FAQ pour suggestions
        faq_categories = ChatbotFAQ.CATEGORIES
        
        # Questions populaires
        popular_faqs = ChatbotFAQ.objects.filter(is_active=True).order_by('-usage_count')[:6]
        
        context.update({
            'conversation': conversation,
            'messages': messages,
            'faq_categories': faq_categories,
            'popular_faqs': popular_faqs,
        })
        
        return context


class ChatbotMessageAPI(View):
    """API pour envoyer et recevoir des messages du chatbot"""
    
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        try:
            data = json.loads(request.body)
            message_content = data.get('message', '').strip()
            session_id = data.get('session_id')
            
            if not message_content:
                return JsonResponse({'error': 'Message vide'}, status=400)
            
            # Récupérer ou créer la conversation
            conversation, created = ChatbotConversation.objects.get_or_create(
                user=request.user,
                session_id=session_id,
                defaults={'is_active': True}
            )
            
            # Enregistrer le message de l'utilisateur
            user_message = ChatbotMessage.objects.create(
                conversation=conversation,
                message_type='USER',
                content=message_content
            )
            
            # Rechercher une réponse automatique
            bot_response = self.find_automatic_response(message_content)
            
            if bot_response:
                # Créer la réponse automatique
                bot_message = ChatbotMessage.objects.create(
                    conversation=conversation,
                    message_type='FAQ',
                    content=bot_response['answer'],
                    faq_used=bot_response['faq']
                )
                
                # Incrémenter le compteur d'utilisation
                bot_response['faq'].increment_usage()
                
                response_data = {
                    'success': True,
                    'response': {
                        'type': 'automatic',
                        'content': bot_response['answer'],
                        'category': bot_response['faq'].get_category_display(),
                        'timestamp': bot_message.created_at.strftime('%H:%M'),
                        'helpful_buttons': True
                    }
                }
            else:
                # Pas de réponse automatique trouvée
                response_data = {
                    'success': True,
                    'response': {
                        'type': 'no_match',
                        'content': "Je n'ai pas trouvé de réponse automatique à votre question. Un syndic vous répondra bientôt.",
                        'suggestions': self.get_suggestions(),
                        'timestamp': timezone.now().strftime('%H:%M'),
                        'helpful_buttons': False
                    }
                }
                
                # Notifier le syndic qu'une question nécessite une réponse humaine
                self.notify_syndic_new_question(conversation, message_content)
            
            return JsonResponse(response_data)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def find_automatic_response(self, message):
        """Rechercher une réponse automatique basée sur les mots-clés"""
        message_lower = message.lower()
        
        # Rechercher dans les FAQs actives
        faqs = ChatbotFAQ.objects.filter(is_active=True)
        
        best_match = None
        best_score = 0
        
        for faq in faqs:
            keywords = [kw.strip().lower() for kw in faq.keywords.split(',')]
            score = 0
            
            for keyword in keywords:
                if keyword in message_lower:
                    score += len(keyword)
            
            if score > best_score:
                best_score = score
                best_match = faq
        
        # Seuil minimum pour considérer une correspondance
        if best_score >= 3:
            return {
                'faq': best_match,
                'answer': best_match.answer,
                'score': best_score
            }
        
        return None
    
    def get_suggestions(self):
        """Obtenir des suggestions de questions populaires"""
        suggestions = ChatbotFAQ.objects.filter(
            is_active=True
        ).order_by('-usage_count')[:3]
        
        return [
            {
                'question': faq.question,
                'category': faq.get_category_display()
            }
            for faq in suggestions
        ]
    
    def notify_syndic_new_question(self, conversation, question):
        """Notifier le syndic qu'une nouvelle question nécessite une réponse humaine"""
        try:
            syndics = User.objects.filter(role__in=['SUPERADMIN', 'SYNDIC'])
            
            notification = Notification.objects.create(
                title="Question chatbot sans réponse",
                message=f"Question de {conversation.user.get_full_name() or conversation.user.username}: {question[:100]}...",
                notification_type="OTHER",
                priority="LOW",
                sender=conversation.user,
                is_active=True,
            )
            notification.recipients.add(*syndics)
            
        except Exception:
            pass


class ChatbotFAQManagementView(ListView):
    """Gestion des FAQ du chatbot - syndics seulement"""
    model = ChatbotFAQ
    template_name = 'finance/chatbot_faq_management.html'
    context_object_name = 'faqs'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = ChatbotFAQ.objects.all()
        
        # Filtres
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(question__icontains=search) | 
                Q(keywords__icontains=search) |
                Q(answer__icontains=search)
            )
        
        return queryset.order_by('-usage_count', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = ChatbotFAQ.CATEGORIES
        context['total_faqs'] = ChatbotFAQ.objects.count()
        context['active_faqs'] = ChatbotFAQ.objects.filter(is_active=True).count()
        return context


class ChatbotFAQCreateView(CreateView):
    """Créer une nouvelle FAQ - syndics seulement"""
    model = ChatbotFAQ
    template_name = 'finance/chatbot_faq_form.html'
    fields = ['question', 'keywords', 'answer', 'category', 'is_active']
    success_url = reverse_lazy('finance:chatbot_faq_management')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('finance:login')
        if request.user.role not in ['SUPERADMIN', 'SYNDIC']:
            messages.error(request, "Accès non autorisé.")
            return redirect('finance:home')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Question fréquente ajoutée avec succès.")
        return super().form_valid(form)
