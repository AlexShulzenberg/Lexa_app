"""
Views приложения vocabulary.
Каждая функция = один URL = одна страница (или API-ответ).
"""

import json
import requests
import re as _re
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Word, Collection, LessonSession, DailyStreak
from .forms import WordForm, CollectionForm
from django.conf import settings
from google import genai
from google.genai import types


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
    from_collection = request.GET.get('collection') or request.POST.get('from_collection')

    if request.method == 'POST':
        form = WordForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Word added successfully!')
            if from_collection:
                return redirect('collection_detail', pk=from_collection)
            return redirect('vocabulary')
    else:
        initial = {}
        if from_collection:
            initial['collection'] = from_collection
        form = WordForm(initial=initial)

    return render(request, 'vocabulary/word_form.html', {
        'form': form,
        'action': 'Add',
        'from_collection': from_collection,
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


def collection_detail(request, pk):
    """
    Страница конкретной коллекции.
    Показывает слова коллекции, позволяет добавить новое слово
    или прикрепить уже существующее из словаря.
    """
    collection = get_object_or_404(Collection, pk=pk)
    words_in = Word.objects.filter(collection=collection)
    # Слова которых ещё нет в этой коллекции — для прикрепления
    words_available = Word.objects.exclude(collection=collection)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'attach':
            # Прикрепить существующее слово к коллекции
            word_id = request.POST.get('word_id')
            word = get_object_or_404(Word, pk=word_id)
            word.collection = collection
            word.save()
            messages.success(request, f'"{word.word}" added to {collection.name}!')

        elif action == 'detach':
            # Открепить слово от коллекции
            word_id = request.POST.get('word_id')
            word = get_object_or_404(Word, pk=word_id)
            word.collection = None
            word.save()
            messages.success(request, f'"{word.word}" removed from collection.')

        return redirect('collection_detail', pk=pk)

    context = {
        'collection': collection,
        'words_in': words_in,
        'words_available': words_available,
    }
    return render(request, 'vocabulary/collection_detail.html', context)


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

def _make_blank_sentence(word):
    """
    Заменяет изучаемое слово в примере предложения на ___.
    Пробует точное совпадение, потом первые 4 символа (основа слова).
    Возвращает строку с пропуском или пустую строку если не нашли.
    """
    sentence = word.example_sentence
    if not sentence:
        return ''

    # Точное совпадение без учёта регистра
    pattern = _re.compile(_re.escape(word.word), _re.IGNORECASE)
    result = pattern.sub('___', sentence, count=1)
    if result != sentence:
        return result

    # Попытка по первым 4 символам (для спряжённых форм)
    if len(word.word) >= 4:
        base = word.word[:4]
        pattern2 = _re.compile(_re.escape(base), _re.IGNORECASE)
        result2 = pattern2.sub('___', sentence, count=1)
        if result2 != sentence:
            return result2

    return ''


def _build_lesson_steps(new_ids, review_ids, all_words):
    """
    Строит очередь шагов урока.
    Новые слова: сначала презентация, потом 2 упражнения.
    Слова на повторение: сразу 2 упражнения.
    """
    import random

    steps = []
    practice_steps = []

    for word in all_words:
        is_new = word.id in new_ids

        # Новые слова получают фазу презентации
        if is_new:
            steps.append({
                'phase': 'presentation',
                'word_id': word.id,
            })

        # Определяем доступные типы упражнений
        available_types = [1, 2]  # FR→RU и RU→FR всегда доступны

        # Тип 3 только если есть пример предложения и слово там найдётся
        if word.example_sentence and _make_blank_sentence(word):
            available_types.append(3)

        # Тип 4 (matching) добавляем если слов достаточно
        # (проверим позже при сборке)
        available_types.append(4)

        # Берём 2 случайных типа для каждого слова
        chosen = random.sample(available_types, min(2, len(available_types)))

        for ex_type in chosen:
            practice_steps.append({
                'phase': 'practice',
                'type': ex_type,
                'word_id': word.id,
            })

    # Перемешиваем упражнения
    random.shuffle(practice_steps)

    # Добавляем choices для типа 3 и пары для типа 4
    all_ids = [w.id for w in all_words]

    for step in practice_steps:
        if step['type'] == 3:
            distractors = [wid for wid in all_ids if wid != step['word_id']]
            if len(distractors) >= 3:
                choices = random.sample(distractors, 3) + [step['word_id']]
                random.shuffle(choices)
                step['choices'] = choices
            else:
                # Мало слов — меняем на тип 1
                step['type'] = 1

        elif step['type'] == 4:
            # Matching: берём 3 пары (текущее слово + 2 случайных)
            distractors = [wid for wid in all_ids if wid != step['word_id']]
            if len(distractors) >= 2:
                pair_ids = random.sample(distractors, 2) + [step['word_id']]
                random.shuffle(pair_ids)
                step['pair_ids'] = pair_ids
            else:
                step['type'] = 1

    steps.extend(practice_steps)
    return steps


def lesson_start(request):
    """
    Собирает слова для урока и строит очередь упражнений.
    Сохраняет всё в Django-сессии.
    """
    import random

    review_ids = list(
        Word.objects.filter(mastery_level__gt=0, mastery_level__lt=90)
        .order_by('last_reviewed')[:8]
        .values_list('id', flat=True)
    )
    new_ids = list(
        Word.objects.filter(mastery_level=0)[:5]
        .values_list('id', flat=True)
    )

    all_ids = list(set(new_ids + review_ids))

    if not all_ids:
        messages.info(request, 'No words available. Add some words first!')
        return redirect('vocabulary')

    all_words = list(Word.objects.filter(id__in=all_ids))
    steps = _build_lesson_steps(set(new_ids), set(review_ids), all_words)

    request.session['lesson_steps'] = steps
    request.session['lesson_step_index'] = 0
    request.session['lesson_correct'] = 0
    request.session['lesson_total_practice'] = sum(
        1 for s in steps if s['phase'] == 'practice'
    )
    request.session['lesson_new_count'] = len(new_ids)
    request.session['lesson_reviewed_count'] = len(review_ids)
    request.session['lesson_start_time'] = timezone.now().isoformat()

    return redirect('lesson_step')


def lesson_step(request):
    """
    Основной view урока. Один URL обрабатывает все фазы и типы.
    GET  → показать текущий шаг
    POST → принять ответ, показать feedback, потом перейти дальше
    """
    steps = request.session.get('lesson_steps', [])
    index = request.session.get('lesson_step_index', 0)

    if not steps or index >= len(steps):
        return redirect('lesson_complete')

    step = steps[index]
    word = get_object_or_404(Word, pk=step['word_id'])
    total = len(steps)
    progress = round((index / total) * 100)

    # ── POST: обработка ответа ──────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action')

        # Презентация: просто листаем дальше
        if step['phase'] == 'presentation' or action == 'next':
            request.session['lesson_step_index'] = index + 1
            request.session.modified = True
            return redirect('lesson_step')

        # Практика: проверяем ответ
        ex_type = step.get('type')
        user_answer = request.POST.get('answer', '').strip()
        correct = False
        correct_answer = ''

        if ex_type == 1:
            # FR → RU: сравниваем с переводом
            correct_answer = word.translation
            correct = user_answer.lower() == word.translation.lower()

        elif ex_type == 2:
            # RU → FR: сравниваем с французским словом
            correct_answer = word.word
            correct = user_answer.lower() == word.word.lower()

        elif ex_type == 3:
            # Fill-in-blank: пользователь нажал на карточку (word_id)
            correct_answer = word.word
            correct = user_answer == str(word.id)

        elif ex_type == 4:
            # Matching: пользователь отправил JSON пар {fr_id: ru_id}
            correct_answer = 'all pairs matched'
            try:
                pairs = json.loads(user_answer)
                # pairs = {"word_id": "word_id", ...} — id должен совпадать сам с собой
                correct = all(k == v for k, v in pairs.items())
            except (json.JSONDecodeError, AttributeError):
                correct = False

        # Обновляем mastery_level
        if correct:
            word.mastery_level = min(100, word.mastery_level + 20)
            request.session['lesson_correct'] = (
                request.session.get('lesson_correct', 0) + 1
            )
        else:
            word.mastery_level = max(0, word.mastery_level - 10)

        word.last_reviewed = timezone.now()
        word.save()

        request.session['lesson_step_index'] = index + 1
        request.session.modified = True

        # Строим контекст для feedback-экрана
        context = {
            'feedback': True,
            'correct': correct,
            'correct_answer': correct_answer,
            'word': word,
            'step': step,
            'current': index + 1,
            'total': total,
            'progress': progress,
        }
        _add_extra_context(context, step, word)
        return render(request, 'vocabulary/lesson.html', context)

    # ── GET: показываем текущий шаг ────────────────────────────────────
    context = {
        'feedback': False,
        'word': word,
        'step': step,
        'current': index + 1,
        'total': total,
        'progress': progress,
    }
    _add_extra_context(context, step, word)
    return render(request, 'vocabulary/lesson.html', context)


def _add_extra_context(context, step, word):
    """Добавляет в контекст данные специфичные для типа упражнения."""
    if step.get('phase') != 'practice':
        return

    ex_type = step.get('type')

    if ex_type == 3 and 'choices' in step:
        choice_words = list(Word.objects.filter(id__in=step['choices']))
        context['choice_words'] = choice_words
        context['blank_sentence'] = _make_blank_sentence(word)

    elif ex_type == 4 and 'pair_ids' in step:
        import random
        pair_words = list(Word.objects.filter(id__in=step['pair_ids']))
        ru_words = pair_words.copy()
        random.shuffle(ru_words)
        context['pair_words'] = pair_words
        context['ru_words'] = ru_words


def lesson_complete(request):
    """Завершение урока: сохраняет статистику."""
    new_count = request.session.get('lesson_new_count', 0)
    reviewed_count = request.session.get('lesson_reviewed_count', 0)
    correct = request.session.get('lesson_correct', 0)
    total_practice = request.session.get('lesson_total_practice', 1)
    start_time_str = request.session.get('lesson_start_time')

    duration = 0
    if start_time_str:
        start_time = timezone.datetime.fromisoformat(start_time_str)
        duration = int((timezone.now() - start_time).total_seconds())

    accuracy = round((correct / total_practice * 100)) if total_practice else 0

    LessonSession.objects.create(
        date=timezone.now().date(),
        words_new=new_count,
        words_reviewed=reviewed_count,
        duration_seconds=duration,
    )
    DailyStreak.objects.get_or_create(date=timezone.now().date())

    for key in ['lesson_steps', 'lesson_step_index', 'lesson_correct',
                'lesson_total_practice', 'lesson_new_count',
                'lesson_reviewed_count', 'lesson_start_time']:
        request.session.pop(key, None)

    messages.success(
        request,
        f'Lesson complete! {correct}/{total_practice} correct ({accuracy}%)'
    )
    return redirect('home')


# ─────────────────────────────────────────────
# API: ПЕРЕВОД
# ─────────────────────────────────────────────

def translate_word(request):
    """
    Переводит французское слово на русский, определяет часть речи 
    и транскрипцию с помощью Gemini API.
    """
    word = request.GET.get('word', '').strip()
    if not word:
        return JsonResponse({'error': 'No word provided'}, status=400)

    # Получаем ключ из settings.py
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        return JsonResponse({'error': 'Gemini API key is missing in settings'}, status=500)

    # Инициализируем клиент
    client = genai.Client(api_key=api_key)

    # Пишем четкий промпт (инструкцию) для ИИ
    prompt = f"""
    Проанализируй французское слово "{word}".
    Верни результат со следующими данными:
    1. translation: точный перевод на русский язык.
    2. transcription: фонетическая транскрипция IPA (например, /e.ku.te/).
    3. part_of_speech: часть речи ('n', 'v', 'adj', 'adv', 'phrase', 'other').
    4. example_sentence: один короткий, естественный пример использования этого слова в предложении на французском языке.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Убедись, что версия модели актуальна для твоего региона/API
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        
        result = json.loads(response.text)
        # Теперь в словаре result будет ключ 'example_sentence'
        return JsonResponse(result)
    
    except Exception as e:
        # Это выведет полную ошибку в консоль VS Code (черное окно внизу)
        print(f"--- Gemini Error: {e} ---") 
        return JsonResponse({'error': str(e)}, status=500)