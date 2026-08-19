from django.contrib import admin
from .models import Booking, BookingPayment, BookingStatusHistory

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('reference', 'buyer', 'photographer', 'status', 'event_date', 'start_time')
    list_filter = ('status', 'event_date')
    search_fields = ('reference', 'buyer__email', 'photographer__user__email')
    readonly_fields = ('created_at', 'updated_at', 'responded_at')

admin.site.register(BookingPayment)
admin.site.register(BookingStatusHistory)
