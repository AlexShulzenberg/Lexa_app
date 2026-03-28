"""Регистрация моделей в административной панели Django."""

from django.contrib import admin
from .models import Collection, Word, LessonSession, DailyStreak

admin.site.register(Collection)
admin.site.register(Word)
admin.site.register(LessonSession)
admin.site.register(DailyStreak)