from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core"

    def ready(self):
        # Eliminate throttling checks across all views safely after settings load
        try:
            from rest_framework.views import APIView
            APIView.check_throttles = lambda self, request: None
        except Exception:
            pass
