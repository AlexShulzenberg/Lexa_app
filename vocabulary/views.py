"""
Views приложения vocabulary.
Каждая функция = один URL = одна страница (или API-ответ).
"""

import json
import re as _re
from .models import Word
from django.db.models import Sum
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
    Показывает только слова, которые пользователь уже встречал в уроке
    (last_reviewed не пустое). Слова добавляются здесь только через урок.
    """
    words = Word.objects.filter(last_reviewed__isnull=False)
    collections = Collection.objects.all()

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
        # Предзаполнение из URL (из OCR клика)
        prefill_word = request.GET.get('word', '')
        if prefill_word:
            initial['word'] = prefill_word
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
    """
    Страница Collections — центр управления словами.
    Три зоны: мои коллекции, очередь изучения, добавление слов.
    """
    all_collections = Collection.objects.all()

    # Очередь новых слов (ещё не видели в уроке)
    new_queue = Word.objects.filter(
        mastery_level=0
    ).order_by('queue_order', 'created_at')

    # Очередь повторения (видели, но не выучили полностью)
    review_queue = Word.objects.filter(
        mastery_level__gt=0,
        mastery_level__lt=100
    ).order_by('queue_order', 'last_reviewed')

    # Форма добавления слова (inline)
    if request.method == 'POST' and request.POST.get('form_type') == 'quick_add':
        form = WordForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Word added to queue!')
            return redirect('collections')
    else:
        form = WordForm()

    context = {
        'collections': all_collections,
        'new_queue': new_queue,
        'review_queue': review_queue,
        'form': form,
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


def collection_import(request):
    """
    Импорт коллекции из JSON-файла.
    Поддерживает загрузку через форму и drag-and-drop (тот же POST).
    """
    if request.method == 'POST':
        uploaded_file = request.FILES.get('collection_file')

        if not uploaded_file:
            messages.error(request, 'No file selected.')
            return redirect('collection_import')

        # Проверяем расширение
        if not uploaded_file.name.endswith('.json'):
            messages.error(request, 'Only .json files are supported.')
            return redirect('collection_import')

        # Проверяем размер (максимум 1MB)
        if uploaded_file.size > 1024 * 1024:
            messages.error(request, 'File too large. Max size is 1MB.')
            return redirect('collection_import')

        try:
            raw = uploaded_file.read().decode('utf-8')
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            messages.error(request, 'Invalid JSON file. Check the file format.')
            return redirect('collection_import')

        # Валидируем структуру
        if 'collection' not in data or 'words' not in data:
            messages.error(
                request,
                'Wrong file structure. Need "collection" and "words" keys.'
            )
            return redirect('collection_import')

        col_data = data['collection']
        words_data = data['words']

        if not isinstance(words_data, list) or len(words_data) == 0:
            messages.error(request, 'Words list is empty.')
            return redirect('collection_import')

        # Допустимые значения part_of_speech
        VALID_POS = {'n', 'v', 'adj', 'adv', 'phrase', 'other'}

        # Создаём коллекцию
        collection = Collection.objects.create(
            name=col_data.get('name', uploaded_file.name),
            description=col_data.get('description', ''),
        )

        created = 0
        skipped = 0
        errors = []

        for i, w in enumerate(words_data, start=1):
            word_text = str(w.get('word', '')).strip()
            translation = str(w.get('translation', '')).strip()

            # Обязательные поля
            if not word_text or not translation:
                skipped += 1
                errors.append(f'Row {i}: missing word or translation')
                continue

            pos = str(w.get('part_of_speech', 'other')).strip()
            if pos not in VALID_POS:
                pos = 'other'

            Word.objects.create(
                word=word_text,
                translation=translation,
                transcription=str(w.get('transcription', '')).strip(),
                part_of_speech=pos,
                example_sentence=str(w.get('example_sentence', '')).strip(),
                collection=collection,
                mastery_level=0,
            )
            created += 1

        msg = f'Collection "{collection.name}" imported: {created} words added.'
        if skipped:
            msg += f' {skipped} skipped (check format).'
        messages.success(request, msg)

        if errors:
            for err in errors[:3]:  # показываем только первые 3 ошибки
                messages.warning(request, err)

        return redirect('collection_detail', pk=collection.pk)

    # GET — показываем страницу загрузки
    return render(request, 'vocabulary/collection_import.html', {
        'pos_choices': Word.PART_OF_SPEECH_CHOICES,
    })
    

# ─────────────────────────────────────────────
# PROGRESS
# ─────────────────────────────────────────────

def progress(request):
    """
    Страница Progress.
    Собирает статистику и передаёт данные для графиков в Chart.js.
    """
    from django.db.models import Sum

    total = Word.objects.count()
    new_count = Word.objects.filter(mastery_level__lt=30).count()
    learning_count = Word.objects.filter(
        mastery_level__gte=30, mastery_level__lt=60
    ).count()
    familiar_count = Word.objects.filter(
        mastery_level__gte=60, mastery_level__lt=90
    ).count()
    mastered_count = Word.objects.filter(mastery_level__gte=90).count()
    streak = DailyStreak.get_current_streak()

    # Агрегируем сессии по датам — суммируем если несколько за день
    sessions_by_date = (
        LessonSession.objects
        .values('date')
        .annotate(
            total_new=Sum('words_new'),
            total_reviewed=Sum('words_reviewed')
        )
        .order_by('date')[:14]
    )

    chart_data = {
        'labels': [str(s['date']) for s in sessions_by_date],
        'new_words': [s['total_new'] for s in sessions_by_date],
        'reviewed_words': [s['total_reviewed'] for s in sessions_by_date],
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
        'chart_data': chart_data,
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

        # Берём count случайных типа для каждого слова
        count = 1
        chosen = random.sample(available_types, min(count, len(available_types)))

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
        .order_by('last_reviewed')[:3]
        .values_list('id', flat=True)
    )
    new_ids = list(
        Word.objects.filter(mastery_level=0)[:3]
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
                # pairs = {"fr_word_id": "ru_word_id"}
                # Правильно если каждый fr_id совпадает со своим ru_id
                correct = all(
                    str(k) == str(v) for k, v in pairs.items()
                )
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
    

# ─────────────────────────────────────────────
# API ДЛЯ УПРАВЛЕНИЯ ОЧЕРЕДЬЮ
# ─────────────────────────────────────────────

def api_queue_reorder(request):
    """
    AJAX: принимает новый порядок слов и сохраняет queue_order.
    Ожидает POST с JSON: {"order": [id1, id2, id3, ...]}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        order = data.get('order', [])
        for position, word_id in enumerate(order):
            Word.objects.filter(pk=word_id).update(queue_order=position)
        return JsonResponse({'ok': True})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


def api_queue_remove(request, pk):
    """AJAX: удаляет слово из системы полностью."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    word = get_object_or_404(Word, pk=pk)
    word.delete()
    return JsonResponse({'ok': True})


def api_queue_postpone(request, pk):
    """
    AJAX: откладывает слово — перемещает вниз очереди
    путём увеличения queue_order на большое число.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    word = get_object_or_404(Word, pk=pk)
    word.queue_order = word.queue_order + 1000
    word.save()
    return JsonResponse({'ok': True})


def api_words_batch_add(request):
    """
    AJAX: принимает список слов от AI-анализа и сохраняет их в БД.
    Ожидает POST с JSON:
    {
      "collection_id": 1,  // или null для новой
      "collection_name": "Новая коллекция",
      "words": [{word, translation, transcription, part_of_speech, example_sentence}, ...]
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        words_data = data.get('words', [])
        collection_id = data.get('collection_id')
        collection_name = data.get('collection_name', 'Imported')

        if collection_id:
            collection = get_object_or_404(Collection, pk=collection_id)
        else:
            collection = Collection.objects.create(
                name=collection_name,
                description='Imported via AI text analysis'
            )

        VALID_POS = {'n', 'v', 'adj', 'adv', 'phrase', 'other'}
        created = 0
        for w in words_data:
            pos = w.get('part_of_speech', 'other')
            if pos not in VALID_POS:
                pos = 'other'
            Word.objects.create(
                word=str(w.get('word', '')).strip(),
                translation=str(w.get('translation', '')).strip(),
                transcription=str(w.get('transcription', '')).strip(),
                part_of_speech=pos,
                example_sentence=str(w.get('example_sentence', '')).strip(),
                collection=collection,
                mastery_level=0,
            )
            created += 1

        return JsonResponse({
            'ok': True,
            'created': created,
            'collection_id': collection.pk,
            'collection_name': collection.name,
        })
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    

# ─────────────────────────────────────────────
# API: OCR ЧЕРЕЗ GEMINI VISION
# ─────────────────────────────────────────────

def api_ocr(request):
    """
    OCR через OCR.space API — бесплатно, 25000 запросов/месяц.
    Хорошо читает текст на фотографиях книг.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        import base64
        import urllib.request
        import urllib.parse

        data = json.loads(request.body)
        image_data = data.get('image', '')

        if not image_data:
            return JsonResponse({'error': 'No image provided'}, status=400)

        api_key = getattr(settings, 'OCR_SPACE_API_KEY', None)
        if not api_key:
            return JsonResponse({'error': 'OCR_SPACE_API_KEY missing in settings'}, status=500)

        # Отправляем base64 напрямую в OCR.space
        payload = urllib.parse.urlencode({
            'base64Image': image_data,   # сюда идёт data:image/jpeg;base64,....
            'language': 'fre',           # французский язык
            'isOverlayRequired': 'false',
            'detectOrientation': 'true',
            'scale': 'true',             # улучшает качество для фото
            'OCREngine': '2',            # Engine 2 лучше для книг
            'apikey': api_key,
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.ocr.space/parse/image',
            data=payload,
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        # Логируем для диагностики
        print('=== OCR.space result ===')
        print(json.dumps(result, indent=2)[:500])
        print('========================')

        # Проверяем ошибки от OCR.space
        if result.get('IsErroredOnProcessing'):
            error_msg = result.get('ErrorMessage', ['Unknown error'])
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return JsonResponse({'error': f'OCR error: {error_msg}'}, status=422)

        # Извлекаем текст из всех страниц
        parsed_results = result.get('ParsedResults', [])
        if not parsed_results:
            return JsonResponse({'error': 'No text found in image'}, status=422)

        full_text = '\n'.join(
            page.get('ParsedText', '')
            for page in parsed_results
        ).strip()

        print(f'=== Extracted {len(full_text)} chars ===')
        print(full_text[:300])

        if not full_text:
            return JsonResponse({'error': 'No text found. Try a clearer image.'}, status=422)

        return JsonResponse({'text': full_text})

    except Exception as e:
        import traceback
        print('=== OCR Error ===')
        print(traceback.format_exc())
        print('=================')
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────
# API: AI АНАЛИЗ ТЕКСТА ЧЕРЕЗ GEMINI
# ─────────────────────────────────────────────

def api_ai_analyze(request):
    """
    AI анализ текста — извлекает французские слова для изучения.
    Принимает POST с текстом и уровнем.
    Не требует авторизации на сторонних сервисах.
    """
      
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        level = data.get('level', 'intermediate')

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            return JsonResponse({'error': 'Gemini API key missing'}, status=500)

        level_labels = {
            'beginner':     'A1-A2 (beginner)',
            'intermediate': 'B1-B2 (intermediate)',
            'advanced':     'C1-C2 (advanced)',
        }
        level_label = level_labels.get(level, 'B1-B2 (intermediate)')

        client = genai.Client(api_key=api_key)

        prompt = f"""You are a French language teacher creating vocabulary lists.
Analyze this French text and extract words suitable for {level_label} learners.
Select only real French words (not proper nouns, not numbers).
Extract up to 10 most useful words.
Return ONLY a valid JSON array with no other text, markdown or explanation:
[
  {{
    "word": "french word in infinitive/base form",
    "translation": "Russian translation",
    "transcription": "/IPA transcription/",
    "part_of_speech": "n or v or adj or adv or phrase or other",
    "example_sentence": "Short example sentence using this word"
  }}
]

Text to analyze:
{text[:1500]}"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
            ),
        )

        result = json.loads(response.text)

        # Gemini иногда возвращает dict вместо list
        if isinstance(result, dict):
            result = result.get('words', [])

        return JsonResponse({'words': result})

    except Exception as e:
        error_str = str(e)

        if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
            return JsonResponse({
                'error': 'AI limit reached. Please try again in a few minutes.'
            }, status=429)

        return JsonResponse({'error': error_str}, status=500)

def api_translate_batch(request):
    """
    Переводит список слов одним запросом к Gemini.
    Принимает: {"words": ["mot", "livre", "grand", ...]}
    Возвращает: {"translations": {"mot": "слово", "livre": "книга", ...}}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        words = data.get('words', [])

        if not words:
            return JsonResponse({'translations': {}})

        # Ограничиваем количество слов
        words = words[:100]

        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            return JsonResponse({'error': 'Gemini API key missing'}, status=500)

        client = genai.Client(api_key=api_key)

        words_list = '\n'.join(f'- {w}' for w in words)

        prompt = f"""Translate these French words to Russian.
Return ONLY a valid JSON object where key=French word, value=Russian translation.
Keep keys exactly as given (lowercase).
Example: {{"mot": "слово", "grand": "большой"}}

Words to translate:
{words_list}"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
            ),
        )

        translations = json.loads(response.text)

        # Убеждаемся что это словарь
        if not isinstance(translations, dict):
            translations = {}

        print(f'=== Batch translated {len(translations)} words ===')

        return JsonResponse({'translations': translations})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)