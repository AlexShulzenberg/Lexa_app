"""
URL-маршруты приложения vocabulary.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Главная страница
    path('', views.home, name='home'),

    # Словарь — список всех слов
    path('vocabulary/', views.vocabulary_list, name='vocabulary'),

    # Прогресс — статистика
    path('progress/', views.progress, name='progress'),

    # Коллекции — управление папками слов
    path('collections/', views.collections, name='collections'),

    # --- CRUD для слов ---
    path('word/add/', views.word_add, name='word_add'),
    path('word/<int:pk>/edit/', views.word_edit, name='word_edit'),
    path('word/<int:pk>/delete/', views.word_delete, name='word_delete'),

    # --- CRUD для коллекций ---
    path('collection/add/', views.collection_add, name='collection_add'),
    path('collection/<int:pk>/edit/', views.collection_edit, name='collection_edit'),
    path('collection/<int:pk>/delete/', views.collection_delete, name='collection_delete'),
    path('collection/<int:pk>/', views.collection_detail, name='collection_detail'),
    path('collection/import/', views.collection_import, name='collection_import'),

    # --- Урок ---
    path('lesson/', views.lesson_start, name='lesson_start'),
    path('lesson/step/', views.lesson_step, name='lesson_step'),
    path('lesson/complete/', views.lesson_complete, name='lesson_complete'),

    # --- API для перевода (вызывается из JS) ---
    path('api/translate/', views.translate_word, name='translate_word'),

    # --- API для очереди ---
    path('api/queue/reorder/', views.api_queue_reorder, name='api_queue_reorder'),
    path('api/queue/remove/<int:pk>/', views.api_queue_remove, name='api_queue_remove'),
    path('api/queue/postpone/<int:pk>/', views.api_queue_postpone, name='api_queue_postpone'),
    path('api/words/batch-add/', views.api_words_batch_add, name='api_words_batch_add'),
    path('api/ocr/', views.api_ocr, name='api_ocr'),
    path('api/ai-analyze/', views.api_ai_analyze, name='api_ai_analyze'),
    path('api/translate-batch/', views.api_translate_batch, name='api_translate_batch'),

]