"""
Модели базы данных для приложения Lexa.
Каждый класс = одна таблица в БД.
"""

from django.db import models
from django.utils import timezone


class Collection(models.Model):
    """
    Коллекция слов — это папка/тема (например 'Бизнес', 'Фильмы').
    Создаётся раньше Word, потому что Word ссылается на Collection.
    """

    name = models.CharField(max_length=100)
    # CharField = строка с ограничением длины.

    description = models.TextField(blank=True, default='')
    # TextField = длинный текст без ограничения.

    created_at = models.DateTimeField(auto_now_add=True)
    # auto_now_add=True = дата заполняется автоматически при создании записи.

    def __str__(self):
        return self.name

    def word_count(self):
        """Сколько слов в коллекции."""
        return self.word_set.count()
        # word_set — автоматическое обратное имя. Django создаёт его сам
        # когда видит ForeignKey(Collection) в модели Word.

    def mastery_percent(self):
        """Средний процент изученности слов в коллекции."""
        words = self.word_set.all()
        if not words:
            return 0
        total = sum(w.mastery_level for w in words)
        return round(total / words.count())

    class Meta:
        ordering = ['name']
        # По умолчанию коллекции будут отсортированы по имени.


class Word(models.Model):
    """
    Главная модель — одно слово.
    Содержит само слово, перевод, пример и уровень изученности.
    """

    PART_OF_SPEECH_CHOICES = [
        ('n', 'noun'),
        ('v', 'verb'),
        ('adj', 'adjective'),
        ('adv', 'adverb'),
        ('phrase', 'phrase'),
        ('other', 'other'),
    ]
    # choices = выпадающий список в форме. Храним короткий код, показываем полное название.

    word = models.CharField(max_length=200)
    translation = models.CharField(max_length=200)
    transcription = models.CharField(max_length=200, blank=True, default='')
    part_of_speech = models.CharField(
        max_length=10,
        choices=PART_OF_SPEECH_CHOICES,
        default='other'
    )
    example_sentence = models.TextField(blank=True, default='')

    mastery_level = models.IntegerField(default=0)
    # 0-100. 0 = новое, 100 = полностью выучено.
    # Почему IntegerField а не проценты в строке:
    # так мы можем делать фильтры: mastery_level__gte=70

    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    # ForeignKey = связь "много к одному". Много слов → одна коллекция.
    # on_delete=SET_NULL: если коллекция удалена, слово остаётся (поле = NULL).
    # null=True: разрешаем NULL в БД. blank=True: поле необязательно в форме.

    created_at = models.DateTimeField(auto_now_add=True)
    last_reviewed = models.DateTimeField(null=True, blank=True)
    # null=True потому что новое слово ещё ни разу не повторялось.

    def __str__(self):
        return f"{self.word} — {self.translation}"

    def mastery_label(self):
        """Человекочитаемый уровень для шаблонов."""
        if self.mastery_level < 30:
            return 'New'
        if self.mastery_level < 60:
            return 'Learning'
        if self.mastery_level < 90:
            return 'Familiar'
        return 'Mastered'

    def mastery_color(self):
        """CSS-класс для цветовой индикации уровня."""
        if self.mastery_level < 30:
            return 'mastery-new'
        if self.mastery_level < 60:
            return 'mastery-learning'
        if self.mastery_level < 90:
            return 'mastery-familiar'
        return 'mastery-mastered'

    class Meta:
        ordering = ['-created_at']
        # Новые слова показываются первыми (минус = обратный порядок).


class LessonSession(models.Model):
    """
    Одна сессия обучения. Создаётся каждый раз когда пользователь
    нажимает Start lesson и завершает урок.
    Нужна для графиков на странице Progress.
    """

    date = models.DateField(default=timezone.now)
    # DateField (без времени) — нам важен только день, не час.

    words_new = models.IntegerField(default=0)
    # Сколько новых слов показано в этом уроке.

    words_reviewed = models.IntegerField(default=0)
    # Сколько слов на повторение.

    duration_seconds = models.IntegerField(default=0)
    # Время урока в секундах. Посчитаем через JS: start_time и end_time.

    words_studied = models.ManyToManyField(Word, blank=True)
    # ManyToMany: один урок содержит много слов, одно слово — во многих уроках.
    # blank=True: можно создать сессию без слов (пустой урок).

    def __str__(self):
        return f"Lesson {self.date} — {self.words_new + self.words_reviewed} words"

    class Meta:
        ordering = ['-date']


class DailyStreak(models.Model):
    """
    Один день занятий. Streak = количество подряд идущих дат в этой таблице.
    Запись создаётся автоматически при завершении урока.
    """

    date = models.DateField(unique=True)
    # unique=True: один день = одна запись. Нельзя добавить один день дважды.

    def __str__(self):
        return str(self.date)

    @classmethod
    def get_current_streak(cls):
        """
        Считает текущий streak: сколько дней подряд были занятия.
        Метод класса — вызывается как DailyStreak.get_current_streak().
        """
        today = timezone.now().date()
        streak = 0
        current_date = today

        while cls.objects.filter(date=current_date).exists():
            streak += 1
            current_date -= timezone.timedelta(days=1)

        return streak

    class Meta:
        ordering = ['-date']