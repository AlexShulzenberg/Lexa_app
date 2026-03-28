"""
Views приложения vocabulary.
Каждая функция = один URL = одна страница (или API-ответ).
"""

import json
import requests
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Word, Collection, LessonSession, DailyStreak
from .forms import WordForm, CollectionForm


# ─────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────

def home(request):
    """
    Главная страница.
    Показывает статус обучения: слова к повторению,
    новые слова, streak, последние активности.
    """
    total_words = Word.objects.count()
    words_to_review = Word.objects.filter(
        mastery_level__lt=100,
        last_reviewed__isnull=False
    ).count()
    new_words = Word.objects.filter(mastery_level=0).count()
    streak = DailyStreak.get_current_streak()

    recent_sessions = LessonSession.objects.all()[:3]
    recent_words = Word.objects.exclude(last_reviewed=None).order_by('-last_reviewed')[:5]

    context = {
        'total_words': total_words,
        'words_to_review': words_to_review,
        'new_words': new_words,
        'streak': streak,
        'recent_sessions': recent_sessions,
        'recent_words': recent_words,
    }
    return render(request, 'vocabulary/home.html', context)


# ─────────────────────────────────────────────
# VOCABULARY LIST
# ─────────────────────────────────────────────

def vocabulary_list(request):
    """
    Страница Vocabulary.
    Список всех слов с фильтрацией по уровню и коллекции.
    """
    words = Word.objects.all()
    collections = Collection.objects.all()

    # Фильтры из GET-параметров (?mastery=new&collection=1)
    mastery_filter = request.GET.get('mastery', '')
    collection_filter = request.GET.get('collection', '')
    search_query = request.GET.get('search', '')

    if mastery_filter == 'new':
        words = words.filter(mastery_level__lt=30)
    elif mastery_filter == 'learning':
        words = words.filter(mastery_level__gte=30, mastery_level__lt=60)
    elif mastery_filter == 'familiar':
        words = words.filter(mastery_level__gte=60, mastery_level__lt=90)
    elif mastery_filter == 'mastered':
        words = words.filter(mastery_level__gte=90)

    if collection_filter:
        words = words.filter(collection__id=collection_filter)

    if search_query:
        words = words.filter(word__icontains=search_query)
        # icontains = поиск без учёта регистра, частичное совпадение

    context = {
        'words': words,
        'collections': collections,
        'mastery_filter': mastery_filter,
        'collection_filter': collection_filter,
        'search_query': search_query,
    }
    return render(request, 'vocabulary/vocabulary.html', context)


# ─────────────────────────────────────────────
# WORD CRUD
# ─────────────────────────────────────────────

def word_add(request):
    """Форма добавления нового слова."""
    if request.method == 'POST':
        form = WordForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Word added successfully!')
            return redirect('vocabulary')
    else:
        form = WordForm()

    return render(request, 'vocabulary/word_form.html', {
        'form': form,
        'action': 'Add',
    })


def word_edit(request, pk):
    """Форма редактирования существующего слова."""
    word = get_object_or_404(Word, pk=pk)
    # get_object_or_404: если слово не найдено — показывает страницу 404

    if request.method == 'POST':
        form = WordForm(request.POST, instance=word)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{word.word}" updated successfully!')
            return redirect('vocabulary')
    else:
        form = WordForm(instance=word)

    return render(request, 'vocabulary/word_form.html', {
        'form': form,
        'action': 'Edit',
        'word': word,
    })


def word_delete(request, pk):
    """Удаление слова. Только POST-запрос (защита от случайного удаления)."""
    word = get_object_or_404(Word, pk=pk)
    if request.method == 'POST':
        word_text = word.word
        word.delete()
        messages.success(request, f'"{word_text}" deleted.')
    return redirect('vocabulary')


# ─────────────────────────────────────────────
# COLLECTIONS
# ─────────────────────────────────────────────

def collections(request):
    """Страница Collections. Список всех коллекций."""
    all_collections = Collection.objects.all()
    context = {
        'collections': all_collections,
    }
    return render(request, 'vocabulary/collections.html', context)


def collection_add(request):
    """Форма создания новой коллекции."""
    if request.method == 'POST':
        form = CollectionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Collection created!')
            return redirect('collections')
    else:
        form = CollectionForm()

    return render(request, 'vocabulary/collection_form.html', {
        'form': form,
        'action': 'Create',
    })


def collection_edit(request, pk):
    """Форма редактирования коллекции."""
    collection = get_object_or_404(Collection, pk=pk)
    if request.method == 'POST':
        form = CollectionForm(request.POST, instance=collection)
        if form.is_valid():
            form.save()
            messages.success(request, 'Collection updated!')
            return redirect('collections')
    else:
        form = CollectionForm(instance=collection)

    return render(request, 'vocabulary/collection_form.html', {
        'form': form,
        'action': 'Edit',
        'collection': collection,
    })


def collection_delete(request, pk):
    """Удаление коллекции."""
    collection = get_object_or_404(Collection, pk=pk)
    if request.method == 'POST':
        collection.delete()
        messages.success(request, 'Collection deleted.')
    return redirect('collections')


# ─────────────────────────────────────────────
# PROGRESS
# ─────────────────────────────────────────────

def progress(request):
    """
    Страница Progress.
    Собирает статистику и передаёт данные для графиков в Chart.js.
    """
    total = Word.objects.count()
    new_count = Word.objects.filter(mastery_level__lt=30).count()
    learning_count = Word.objects.filter(mastery_level__gte=30, mastery_level__lt=60).count()
    familiar_count = Word.objects.filter(mastery_level__gte=60, mastery_level__lt=90).count()
    mastered_count = Word.objects.filter(mastery_level__gte=90).count()
    streak = DailyStreak.get_current_streak()

    # Данные для графика активности (последние 7 дней)
    sessions = LessonSession.objects.order_by('date')[:14]
    chart_labels = [str(s.date) for s in sessions]
    chart_new = [s.words_new for s in sessions]
    chart_reviewed = [s.words_reviewed for s in sessions]

    # Передаём как JSON чтобы Chart.js мог прочитать
    chart_data = {
        'labels': chart_labels,
        'new_words': chart_new,
        'reviewed_words': chart_reviewed,
    }

    recent_words = Word.objects.exclude(
        last_reviewed=None
    ).order_by('-last_reviewed')[:10]

    context = {
        'total': total,
        'new_count': new_count,
        'learning_count': learning_count,
        'familiar_count': familiar_count,
        'mastered_count': mastered_count,
        'streak': streak,
        'chart_data_json': json.dumps(chart_data),
        'recent_words': recent_words,
    }
    return render(request, 'vocabulary/progress.html', context)


# ─────────────────────────────────────────────
# LESSON
# ─────────────────────────────────────────────

def lesson_start(request):
    """
    Начало урока.
    Собирает слова для изучения и сохраняет их в сессии Django.
    Сессия Django — это временное хранилище данных для одного пользователя.
    """
    # Приоритет: сначала слова с низким mastery, потом новые
    words_to_review = list(
        Word.objects.filter(
            mastery_level__gt=0,
            mastery_level__lt=90
        ).order_by('last_reviewed')[:10].values_list('id', flat=True)
    )
    new_words = list(
        Word.objects.filter(
            mastery_level=0
        )[:10].values_list('id', flat=True)
    )

    all_word_ids = words_to_review + new_words

    if not all_word_ids:
        messages.info(request, 'No words available. Add some words first!')
        return redirect('vocabulary')

    # Сохраняем список слов и прогресс в сессии
    request.session['lesson_word_ids'] = all_word_ids
    request.session['lesson_index'] = 0
    request.session['lesson_new_count'] = len(new_words)
    request.session['lesson_reviewed_count'] = len(words_to_review)
    request.session['lesson_start_time'] = timezone.now().isoformat()

    return redirect('lesson_card')


def lesson_card(request):
    """
    Показывает карточку текущего слова.
    GET = показать слово, POST = ответить (знаю/не знаю).
    """
    word_ids = request.session.get('lesson_word_ids', [])
    index = request.session.get('lesson_index', 0)

    if not word_ids or index >= len(word_ids):
        return redirect('lesson_complete')

    word = get_object_or_404(Word, pk=word_ids[index])
    total = len(word_ids)

    if request.method == 'POST':
        result = request.POST.get('result')  # 'know' или 'dont_know'

        # Обновляем mastery_level
        if result == 'know':
            word.mastery_level = min(100, word.mastery_level + 20)
        else:
            word.mastery_level = max(0, word.mastery_level - 10)

        word.last_reviewed = timezone.now()
        word.save()

        request.session['lesson_index'] = index + 1
        request.session.modified = True
        # modified=True: говорим Django что сессия изменилась

        return redirect('lesson_card')

    context = {
        'word': word,
        'current': index + 1,
        'total': total,
        'progress_percent': round((index / total) * 100),
    }
    return render(request, 'vocabulary/lesson.html', context)


def lesson_complete(request):
    """
    Завершение урока.
    Сохраняет LessonSession и DailyStreak.
    """
    new_count = request.session.get('lesson_new_count', 0)
    reviewed_count = request.session.get('lesson_reviewed_count', 0)
    start_time_str = request.session.get('lesson_start_time')

    duration = 0
    if start_time_str:
        start_time = timezone.datetime.fromisoformat(start_time_str)
        duration = int((timezone.now() - start_time).total_seconds())

    # Сохраняем сессию урока
    LessonSession.objects.create(
        date=timezone.now().date(),
        words_new=new_count,
        words_reviewed=reviewed_count,
        duration_seconds=duration,
    )

    # Записываем сегодня в streak (get_or_create: создаст если нет, иначе вернёт существующий)
    DailyStreak.objects.get_or_create(date=timezone.now().date())

    # Очищаем данные урока из сессии
    for key in ['lesson_word_ids', 'lesson_index', 'lesson_new_count',
                'lesson_reviewed_count', 'lesson_start_time']:
        request.session.pop(key, None)

    messages.success(request, f'Lesson complete! {new_count + reviewed_count} words studied.')
    return redirect('home')


# ─────────────────────────────────────────────
# API: ПЕРЕВОД
# ─────────────────────────────────────────────

def translate_word(request):
    """
    API-эндпоинт для перевода слова через MyMemory API.
    Вызывается из JavaScript (fetch) на странице добавления слова.
    Возвращает JSON.
    """
    word = request.GET.get('word', '')
    if not word:
        return JsonResponse({'error': 'No word provided'}, status=400)

    try:
        url = f"https://api.mymemory.translated.net/get?q={word}&langpair=en|ru"
        response = requests.get(url, timeout=5)
        data = response.json()
        translation = data['responseData']['translatedText']
        return JsonResponse({'translation': translation})
    except Exception:
        return JsonResponse({'error': 'Translation failed'}, status=500)